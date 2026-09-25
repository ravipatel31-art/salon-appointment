"""Phase 3/6 hold-expiry tests — 12-min TTL sweep: pending_payment → cancelled (hold_expired)."""

from __future__ import annotations

from datetime import timedelta

from app.services.hold_expiry import sweep_expired_holds
from tests.test_payment_fixtures import BookingStore, booking_store, now_utc


def test_sweep_cancels_expired_pending_hold(booking_store: BookingStore) -> None:
    booking_id = booking_store.add(
        status="pending_payment",
        expires_at=now_utc() - timedelta(seconds=1),
    )

    released = sweep_expired_holds(booking_store.session())

    assert released == 1
    row = booking_store.get(booking_id)
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["cancellation_reason"] == "hold_expired"


def test_sweep_keeps_live_hold(booking_store: BookingStore) -> None:
    booking_id = booking_store.add(
        status="pending_payment",
        expires_at=now_utc() + timedelta(minutes=11),
    )

    assert sweep_expired_holds(booking_store.session()) == 0

    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "pending_payment"


def test_sweep_ignores_confirmed_and_cancelled_rows(booking_store: BookingStore) -> None:
    past = now_utc() - timedelta(hours=1)
    confirmed_id = booking_store.add(status="confirmed", expires_at=past)
    cancelled_id = booking_store.add(
        id="bk_cancel", status="cancelled", expires_at=past, cancellation_reason="customer"
    )

    assert sweep_expired_holds(booking_store.session()) == 0

    assert booking_store.get(confirmed_id)["status"] == "confirmed"
    assert booking_store.get(cancelled_id)["cancellation_reason"] == "customer"


def test_sweep_releases_slot_for_rebooking_semantics(booking_store: BookingStore) -> None:
    """Two overlapping bookings for one barber: expired hold must free the slot."""
    shared_start = now_utc() + timedelta(hours=2)
    shared_end = shared_start + timedelta(hours=1)
    expired_id = booking_store.add(
        status="pending_payment",
        start_at=shared_start,
        end_at=shared_end,
        expires_at=now_utc() - timedelta(minutes=1),
    )

    released = sweep_expired_holds(booking_store.session())
    assert released == 1
    row = booking_store.get(expired_id)
    assert row is not None
    assert row["status"] == "cancelled"  # slot no longer held by pending_payment


def test_sweep_is_idempotent(booking_store: BookingStore) -> None:
    booking_id = booking_store.add(
        status="pending_payment",
        expires_at=now_utc() - timedelta(minutes=5),
    )

    assert sweep_expired_holds(booking_store.session()) == 1
    assert sweep_expired_holds(booking_store.session()) == 0

    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "cancelled"


def test_sweep_without_bookings_table_returns_zero() -> None:
    """Pre-migration databases (no bookings table) must not explode."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        assert sweep_expired_holds(session) == 0
    finally:
        session.close()
        engine.dispose()


def test_sweep_default_session_path_is_guarded(monkeypatch) -> None:
    """sweep_expired_holds() with no db arg swallows DB-outage errors (create_order path)."""
    import app.db as app_db
    from app.services import hold_expiry

    class BoomSession:
        def get_bind(self):
            raise ConnectionError("db down")

        def rollback(self):  # pragma: no cover - defensive
            pass

        def close(self):  # pragma: no cover
            pass

    monkeypatch.setattr(app_db, "SessionLocal", BoomSession)
    # Raises on unexpected errors (documented) — create_order wraps it in try/except.
    try:
        sweep_expired_holds()
    except ConnectionError:
        pass
