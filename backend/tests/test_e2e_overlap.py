"""Phase 6 — barber double-booking / overlap hardening.

One barber, one customer at a time: half-open overlap on
``(barber_id, [start_at, end_at))`` for ``pending_payment`` (unexpired) and
``confirmed`` rows. TestClient requests are serial, so the "race" is exercised
deterministically as conflicting-window attempts from two customers — the same
invariant a true concurrent race must uphold.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutil import utcnow
from app.db import SessionLocal
from app.models import Booking
from app.services.availability import has_overlap
from app.services.hold_expiry import sweep_expired_holds
from tests.conftest import (  # noqa: F401 — helpers
    confirm_booking,
    create_booking,
    future_day,
    service_ids,
    slot_utc,
)


def test_double_booking_race_overlapping_slots_single_winner(
    client, customer_headers, customer2_headers
):
    """Two customers racing overlapping windows on one barber → exactly one hold."""
    day = future_day()
    sid = service_ids(client)["Haircut"]  # 60 min

    # Customer 1 wins the 10:00–11:00 race.
    first = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    assert first["booking"]["status"] == "pending_payment"

    # Customer 2's overlapping attempts all lose with 409 slot_unavailable.
    for hour, minute, why in (
        (10, 0, "exact same slot"),
        (10, 30, "starts inside the hold"),
        (9, 45, "09:45+60m ends 10:45 — overlaps tail"),
    ):
        resp = create_booking(
            client,
            customer2_headers,
            service_id=sid,
            day=day,
            hour=hour,
            minute=minute,
            expect=409,
        )
        assert resp["detail"] == "slot_unavailable", why

    # Shorter service straddling the hold is also blocked.
    beard = service_ids(client)["Beard trim"]  # 15 min
    resp = create_booking(
        client, customer2_headers, service_id=beard, day=day, hour=10, minute=45, expect=409
    )
    assert resp["detail"] == "slot_unavailable"

    # Adjacent half-open boundaries are free: 09:00–10:00 and 11:00–12:00.
    create_booking(client, customer2_headers, service_id=sid, day=day, hour=9)
    create_booking(client, customer2_headers, service_id=sid, day=day, hour=11)

    # After customer 1 confirms, the slot stays blocked for customer 2.
    confirm_booking(client, customer_headers, first)
    resp = create_booking(
        client, customer2_headers, service_id=sid, day=day, hour=10, expect=409
    )
    assert resp["detail"] == "slot_unavailable"

    # A different barber is unaffected — same instant, no conflict.
    create_booking(
        client, customer2_headers, service_id=sid, barber_id=2, day=day, hour=10
    )

    # Exactly one booking exists on barber 1 for 10:00–11:00.
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Booking).where(
                Booking.barber_id == 1,
                Booking.start_at == slot_utc(day, 10, 0),
            )
        ).all()
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].status == "confirmed"


def test_overlap_half_open_boundary_matrix(client, customer_headers, db):
    """``has_overlap`` treats windows as half-open [start, end) on both sides."""
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    confirm_booking(client, customer_headers, created)

    start = slot_utc(day, 10, 0)
    end = start + timedelta(minutes=60)
    now = utcnow()

    assert has_overlap(db, 1, start, end, now) is True  # identical window
    assert has_overlap(db, 1, start - timedelta(minutes=30), start, now) is False  # [09:30,10:00)
    assert has_overlap(db, 1, end, end + timedelta(minutes=15), now) is False  # [11:00,11:15)
    assert has_overlap(db, 1, start - timedelta(minutes=15), start + timedelta(minutes=15), now) is True
    assert has_overlap(db, 1, start + timedelta(minutes=45), end + timedelta(minutes=15), now) is True
    assert has_overlap(db, 2, start, end, now) is False  # other barber free


def test_verify_payment_rechecks_overlap_before_confirm(
    client, customer_headers, customer, db
):
    """AGENTS.md: Razorpay verify re-checks overlap before ``confirmed``."""
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    bid = created["booking"]["id"]
    payment = created["payment"]

    # Rival confirmed booking appears between order creation and checkout
    # completion (inserted directly — the API would have 409'd the hold).
    start = slot_utc(day, 10, 0)
    db.add(
        Booking(
            booking_ref="SL-E2E-RIVAL-01",
            user_id=customer["user"]["id"],
            service_id=sid,
            barber_id=1,
            addons=[],
            start_at=start,
            end_at=start + timedelta(minutes=60),
            duration_minutes=60,
            total_amount=100,
            advance_amount=50,
            balance_amount=50,
            online_amount_paid=50,
            status="confirmed",
            expires_at=None,
            notes="rival",
        )
    )
    db.commit()

    resp = client.post(
        f"/bookings/{bid}/verify-payment",
        headers=customer_headers,
        json={
            "razorpay_order_id": payment["razorpay_order_id"],
            "razorpay_payment_id": "pay_race",
            "razorpay_signature": "sig",  # fake_payments verifies True
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "slot_unavailable"

    db.expire_all()
    row = db.get(Booking, uuid.UUID(bid))
    assert row.status == "pending_payment"  # never confirmed
    assert row.online_amount_paid == 0


def test_expired_hold_sweep_frees_slot_for_rebooking(
    client, customer_headers, customer2_headers, db
):
    """Hold-expiry job releases the slot; late verify on the old hold fails."""
    day = future_day()
    sid = service_ids(client)["Haircut"]
    first = create_booking(client, customer_headers, service_id=sid, day=day, hour=16)
    bid = first["booking"]["id"]
    payment = first["payment"]

    # 12-minute TTL lapses.
    row = db.get(Booking, uuid.UUID(bid))
    row.expires_at = utcnow() - timedelta(seconds=30)
    db.commit()

    # Sweep (the integration hold-expiry job) cancels the hold → slot free.
    assert sweep_expired_holds() == 1
    db.expire_all()
    assert db.get(Booking, uuid.UUID(bid)).status == "cancelled"

    # Customer 2 now wins the previously-blocked slot.
    second = create_booking(client, customer2_headers, service_id=sid, day=day, hour=16)
    assert second["booking"]["status"] == "pending_payment"
    assert second["booking"]["id"] != bid

    # Customer 1's late checkout cannot confirm a cancelled hold.
    resp = client.post(
        f"/bookings/{bid}/verify-payment",
        headers=customer_headers,
        json={
            "razorpay_order_id": payment["razorpay_order_id"],
            "razorpay_payment_id": "pay_too_late",
            "razorpay_signature": "sig",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_status"  # status is now cancelled
    db.expire_all()
    assert db.get(Booking, uuid.UUID(bid)).status == "cancelled"
