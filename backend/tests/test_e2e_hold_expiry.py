"""Phase 6 — hold-expiry job tests on the real bookings schema.

Post CONTRACT_CHANGE (2026-09-23): migration ``0003_cancellation_reason`` +
ORM column ship ``bookings.cancellation_reason`` on the real schema.
``hold_expiry`` still reflects the table and sets ``hold_expired`` only when
the column exists; these tests pin:
- sweep sets ``cancelled`` + ``cancellation_reason='hold_expired'`` (CHECK
  allows the value; ALTER helper is idempotent/skippable if already present);
- API read path reflects the release end-to-end on the post-delta schema;
- live holds untouched; worker env-gate + start idempotency intact.
"""

from __future__ import annotations

import sys
import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.timeutil import ensure_utc, utcnow
from app.models import Booking
from app.services import hold_expiry
from app.services.hold_expiry import sweep_expired_holds
from tests.conftest import (  # noqa: F401 — helpers
    create_booking,
    future_day,
    service_ids,
)


def _add_cancellation_reason_column(db) -> None:
    """Salon-backend owns migrations; simulate the column landing *if missing*.

    Post-delta the ORM/migration 0003 already ships the column — skip the
    ALTER so the helper stays idempotent and never collides.
    """
    if "cancellation_reason" in _column_names(db):
        return
    db.execute(text("ALTER TABLE bookings ADD COLUMN cancellation_reason VARCHAR(32)"))
    db.commit()


def _column_names(db) -> set[str]:
    rows = db.execute(text("PRAGMA table_info(bookings)")).fetchall()
    return {row[1] for row in rows}  # PRAGMA → (cid, name, type, ...)


def test_hold_sweep_sets_hold_expired_reason_when_column_exists(
    client, customer_headers, db
):
    """CONTRACT_CHANGE observability: cancelled + cancellation_reason='hold_expired'."""
    _add_cancellation_reason_column(db)  # no-op when migration 0003 already shipped
    assert "cancellation_reason" in _column_names(db)

    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    bid = created["booking"]["id"]
    ref = created["booking"]["booking_ref"]

    # TTL lapses.
    row = db.get(Booking, uuid.UUID(bid))
    row.expires_at = utcnow() - timedelta(seconds=30)
    db.commit()

    assert sweep_expired_holds() == 1  # own session (background-job path)

    out = db.execute(
        text("SELECT status, cancellation_reason FROM bookings WHERE booking_ref = :ref"),
        {"ref": ref},
    ).mappings().one()
    assert out["status"] == "cancelled"
    assert out["cancellation_reason"] == "hold_expired"

    # Second sweep is a no-op (only pending_payment rows are candidates).
    assert sweep_expired_holds() == 0


def test_hold_sweep_api_reflects_hold_expired_on_shipped_schema(
    client, customer_headers, db
):
    """Post-delta real schema: column ships with 0003 → sweep + API both reflect it."""
    assert "cancellation_reason" in _column_names(db)  # shipped, no ALTER needed

    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=11)
    bid = created["booking"]["id"]
    # Fresh hold: optional field present but null.
    assert created["booking"]["cancellation_reason"] is None

    row = db.get(Booking, uuid.UUID(bid))
    row.expires_at = utcnow() - timedelta(minutes=2)
    db.commit()

    # CHECK constraint on the shipped column accepts 'hold_expired'.
    assert sweep_expired_holds() == 1

    db.expire_all()
    row = db.get(Booking, uuid.UUID(bid))
    assert row.status == "cancelled"
    assert row.cancellation_reason == "hold_expired"

    # API read path reflects the release + reason.
    resp = client.get(f"/bookings/{bid}", headers=customer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_reason"] == "hold_expired"


def test_hold_sweep_leaves_live_hold_untouched_on_real_schema(
    client, customer_headers, db
):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=12)
    bid = created["booking"]["id"]

    assert sweep_expired_holds() == 0  # expires ~12 min ahead

    db.expire_all()
    row = db.get(Booking, uuid.UUID(bid))
    assert row.status == "pending_payment"
    assert row.expires_at is not None
    # Still within the 12-minute window (ensure_utc normalizes SQLite naive values).
    assert ensure_utc(row.expires_at) > utcnow()


def test_hold_expiry_worker_env_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOLD_EXPIRY_WORKER=0 disables auto-start; =1 enables it outside pytest."""
    calls: list[str] = []
    monkeypatch.setattr(
        hold_expiry, "start_hold_expiry_worker", lambda *a, **k: calls.append("start") or True
    )

    # Flag checked before the pytest guard → off never starts.
    monkeypatch.setenv("HOLD_EXPIRY_WORKER", "0")
    hold_expiry._auto_start_worker()
    assert calls == []

    # Flag on: under pytest the guard blocks; simulate a non-pytest runtime.
    monkeypatch.setenv("HOLD_EXPIRY_WORKER", "1")
    pytest_module = sys.modules.pop("pytest")
    try:
        hold_expiry._auto_start_worker()
    finally:
        sys.modules["pytest"] = pytest_module
    assert calls == ["start"]


def test_hold_expiry_worker_start_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """start_hold_expiry_worker spawns exactly one daemon thread across calls."""
    started: list[bool] = []
    real_started_flag = hold_expiry._worker_started
    if real_started_flag:
        pytest.skip("worker already running")

    class FakeThread:
        def __init__(self, *args, **kwargs):
            self.daemon = kwargs.get("daemon")

        def start(self):
            started.append(True)

    class FakeThreading:
        Lock = staticmethod(threading.Lock)
        Thread = FakeThread

    monkeypatch.setattr(hold_expiry, "threading", FakeThreading)
    try:
        assert hold_expiry.start_hold_expiry_worker(0.01) is True
        assert hold_expiry.start_hold_expiry_worker(0.01) is True  # idempotent
        assert len(started) == 1
    finally:
        hold_expiry._worker_started = real_started_flag  # restore module global
