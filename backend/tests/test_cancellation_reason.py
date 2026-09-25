"""Contract delta (2026-09-23): bookings.cancellation_reason — write-side coverage.

Migration 0003_cancellation_reason ships the nullable enum column
(``hold_expired`` | ``customer`` | NULL) on the real schema. Salon-integration's
``hold_expiry.sweep_expired_holds`` reflects the table and sets ``hold_expired``
when the column exists — this test pins that behaviour against the *real*
ORM-created schema (no simulated ALTER), i.e. the post-delta production shape.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import text

from app.core.timeutil import utcnow
from app.models import Booking
from app.services.hold_expiry import sweep_expired_holds
from tests.conftest import (  # noqa: F401 — helpers
    create_booking,
    future_day,
    service_ids,
)


def test_real_schema_ships_cancellation_reason_column(db):
    """0003 → ORM schema contains bookings.cancellation_reason (no ALTER needed)."""
    rows = db.execute(text("PRAGMA table_info(bookings)")).fetchall()
    columns = {row[1] for row in rows}
    assert "cancellation_reason" in columns


def test_hold_sweep_sets_hold_expired_on_real_schema(client, customer_headers, db):
    """Expired unpaid hold on the shipped column → cancelled + hold_expired."""
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=13)
    bid = created["booking"]["id"]
    ref = created["booking"]["booking_ref"]

    # Fresh booking: reason still null while the hold is live.
    assert created["booking"]["cancellation_reason"] is None

    row = db.get(Booking, uuid.UUID(bid))
    row.expires_at = utcnow() - timedelta(seconds=30)
    db.commit()

    assert sweep_expired_holds() == 1

    out = db.execute(
        text(
            "SELECT status, cancellation_reason FROM bookings WHERE booking_ref = :ref"
        ),
        {"ref": ref},
    ).mappings().one()
    assert out["status"] == "cancelled"
    assert out["cancellation_reason"] == "hold_expired"

    # API read path exposes the optional field.
    resp = client.get(f"/bookings/{bid}", headers=customer_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["cancellation_reason"] == "hold_expired"

    # Idempotent second sweep.
    assert sweep_expired_holds() == 0
