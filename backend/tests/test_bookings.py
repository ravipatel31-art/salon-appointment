"""Phase 2 — booking create/hold, advance math, verify, list/get, cancel rules."""

import uuid
from datetime import timedelta

from app.core.timeutil import utcnow
from app.db import SessionLocal
from app.models import Booking
from tests.conftest import (
    ADMIN_PHONE,
    confirm_booking,
    create_booking,
    service_ids,
    slot_utc,
    future_day,
)


def test_create_booking_pending_hold_and_advance_50(client, customer_headers, fake_payments):
    day = future_day()
    sid = service_ids(client)["Haircut"]  # ₹100, 60 min
    before = utcnow()
    resp = create_booking(
        client,
        customer_headers,
        service_id=sid,
        day=day,
        hour=10,
        addons=["wash"],
    )
    booking = resp["booking"]
    payment = resp["payment"]

    assert resp["booking"]["status"] == "pending_payment"
    assert booking["booking_ref"].startswith(f"SL-{day.strftime('%Y%m%d')}-")
    assert booking["duration_minutes"] == 75  # 60 + wash 15
    assert booking["total_amount"] == 130  # 100 + 30
    assert booking["advance_amount"] == 65  # ceil(130 * 0.5)
    assert booking["balance_amount"] == 65
    assert booking["online_amount_paid"] == 0
    assert booking["cancellation_reason"] is None  # optional field, null until cancelled

    # hold TTL = 12 minutes
    expires = __import__("datetime").datetime.fromisoformat(
        booking["expires_at"].replace("Z", "+00:00")
    )
    assert timedelta(minutes=11) <= expires - before <= timedelta(minutes=12, seconds=5)

    # payment object: paise only in razorpay_amount
    assert payment["razorpay_amount"] == 6500
    assert payment["razorpay_currency"] == "INR"
    assert payment["razorpay_order_id"].startswith("order_test_SL-")
    assert payment["key_id"]

    # create_order called with (advance_rupees, booking_ref)
    assert fake_payments.created[-1][0] == 65
    assert fake_payments.created[-1][1] == booking["booking_ref"]

    # ends at start + 75m
    start = __import__("datetime").datetime.fromisoformat(
        booking["start_at"].replace("Z", "+00:00")
    )
    end = __import__("datetime").datetime.fromisoformat(
        booking["end_at"].replace("Z", "+00:00")
    )
    assert end - start == timedelta(minutes=75)


def test_hair_color_flat_advance_100(client, customer_headers, fake_payments):
    day = future_day()
    sid = service_ids(client)["Hair color"]  # variable_advance, price 100
    resp = create_booking(client, customer_headers, service_id=sid, day=day, hour=11)
    booking = resp["booking"]
    assert booking["total_amount"] == 100
    assert booking["advance_amount"] == 100  # flat ₹100 online
    assert booking["balance_amount"] == 0
    assert resp["payment"]["razorpay_amount"] == 10000  # paise
    assert fake_payments.created[-1][0] == 100


def test_advance_uses_ceil_for_odd_totals(client, admin_headers, customer_headers):
    day = future_day()
    create = client.post(
        "/admin/services",
        headers=admin_headers,
        json={"name": "Odd price service", "duration_minutes": 30, "price": 101},
    )
    sid = create.json()["id"]
    resp = create_booking(client, customer_headers, service_id=sid, day=day, hour=12)
    booking = resp["booking"]
    assert booking["total_amount"] == 101
    assert booking["advance_amount"] == 51  # ceil(50.5)
    assert booking["balance_amount"] == 50


def test_conflicting_slot_409(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    # second hold on same slot while first is active
    resp = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=10, expect=409
    )
    assert resp["detail"] == "slot_unavailable"


def test_invalid_slot_rejected_409(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]

    # off the 15-minute grid (10:07)
    resp = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=10, minute=7, expect=409
    )
    assert resp["detail"] == "slot_unavailable"

    # before opening hours (08:00 IST)
    resp = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=8, expect=409
    )
    assert resp["detail"] == "slot_unavailable"

    # doesn't fit before close (19:30 + 60 > 20:00)
    resp = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=19, minute=30, expect=409
    )
    assert resp["detail"] == "slot_unavailable"

    # past date
    from app.core.timeutil import kolkata_date, utcnow

    yesterday = kolkata_date(utcnow()) - timedelta(days=1)
    resp = create_booking(
        client, customer_headers, service_id=sid, day=yesterday, hour=10, expect=409
    )
    assert resp["detail"] == "slot_unavailable"


def test_create_requires_identity_or_auth_and_valid_refs(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    payload = {
        "service_id": sid,
        "addons": [],
        "barber_id": 1,
        "start_at": slot_utc(day, 10).isoformat().replace("+00:00", "Z"),
    }
    # Unauthenticated without guest identity → 400 guest_identity_required
    # (contract 2026-09-24; was 401 before guest checkout).
    resp = client.post("/bookings", json=payload)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "guest_identity_required"

    # Invalid Bearer on the optional-auth header is still rejected.
    resp = client.post(
        "/bookings",
        headers={"Authorization": "Bearer not-a-jwt"},
        json=dict(payload, guest_name="X", guest_phone="9876543210"),
    )
    assert resp.status_code == 401

    # Guest checkout never links to a non-customer (seeded admin phone) —
    # no bearer is minted for admin roles from guest create.
    resp = client.post(
        "/bookings", json=dict(payload, guest_name="X", guest_phone=ADMIN_PHONE)
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "guest_identity_required"

    bad = dict(payload, service_id=9999)
    resp = client.post("/bookings", headers=customer_headers, json=bad)
    assert resp.status_code == 404

    bad = dict(payload, barber_id=9999)
    resp = client.post("/bookings", headers=customer_headers, json=bad)
    assert resp.status_code == 404

    bad = dict(payload, addons=["nope"])
    resp = client.post("/bookings", headers=customer_headers, json=bad)
    assert resp.status_code == 400


def test_verify_payment_success_confirms(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    confirmed = confirm_booking(client, customer_headers, created)
    assert confirmed["status"] == "confirmed"
    assert confirmed["online_amount_paid"] == confirmed["advance_amount"] == 50
    assert confirmed["service_name"] == "Haircut"
    assert confirmed["barber_name"]


def test_verify_payment_bad_signature_400(client, customer_headers, fake_payments):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    fake_payments.verify_result = False
    resp = client.post(
        f"/bookings/{created['booking']['id']}/verify-payment",
        headers=customer_headers,
        json={
            "razorpay_order_id": created["payment"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "bad",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "verification_failed"


def test_verify_payment_order_mismatch_400(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    resp = client.post(
        f"/bookings/{created['booking']['id']}/verify-payment",
        headers=customer_headers,
        json={
            "razorpay_order_id": "order_someone_elses",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "sig",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "order_mismatch"


def test_list_and_get_bookings_scoped_to_owner(
    client, customer_headers, customer2_headers
):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    bid = created["booking"]["id"]

    mine = client.get("/bookings", headers=customer_headers)
    assert mine.status_code == 200
    items = mine.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == bid
    for key in (
        "service_name",
        "barber_name",
        "final_price_at_center",
        "balance_due",
        "status",
        "expires_at",
    ):
        assert key in items[0]

    other = client.get("/bookings", headers=customer2_headers)
    assert other.json()["items"] == []

    got = client.get(f"/bookings/{bid}", headers=customer_headers)
    assert got.status_code == 200
    assert got.json()["id"] == bid

    # other customers can't see it (404, no existence leak)
    assert client.get(f"/bookings/{bid}", headers=customer2_headers).status_code == 404
    assert client.get(f"/bookings/{bid}").status_code == 401

    # invalid uuid
    assert client.get("/bookings/not-a-uuid", headers=customer_headers).status_code == 422


def test_cancel_more_than_2h_before_start(client, customer_headers, fake_payments):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    confirmed = confirm_booking(client, customer_headers, created)
    assert confirmed["online_amount_paid"] == 50

    resp = client.post(
        f"/bookings/{confirmed['id']}/cancel", headers=customer_headers
    )
    assert resp.status_code == 200
    assert resp.json()["booking"]["status"] == "cancelled"
    assert resp.json()["booking"]["cancellation_reason"] == "customer"
    # reason persists on subsequent reads
    got = client.get(f"/bookings/{confirmed['id']}", headers=customer_headers)
    assert got.status_code == 200
    assert got.json()["cancellation_reason"] == "customer"
    # refund enqueued with payment id + rupees
    assert fake_payments.refunded == [("pay_test_123", 50)]


def test_cancel_unpaid_hold_does_not_refund(client, customer_headers, fake_payments):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    resp = client.post(
        f"/bookings/{created['booking']['id']}/cancel", headers=customer_headers
    )
    assert resp.status_code == 200
    assert resp.json()["booking"]["status"] == "cancelled"
    assert resp.json()["booking"]["cancellation_reason"] == "customer"
    assert fake_payments.refunded == []


def test_cancel_within_2h_forbidden(client, customer_headers, fake_payments, db):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    confirmed = confirm_booking(client, customer_headers, created)

    # move the appointment to 1 hour from now (simulate late cancellation)
    row = db.get(Booking, uuid.UUID(confirmed["id"]))
    row.start_at = utcnow() + timedelta(hours=1)
    row.end_at = row.start_at + timedelta(minutes=row.duration_minutes)
    db.commit()

    resp = client.post(f"/bookings/{confirmed['id']}/cancel", headers=customer_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "too_late_to_cancel"
    assert fake_payments.refunded == []

    db.expire_all()
    row = db.get(Booking, uuid.UUID(confirmed["id"]))
    assert row.status == "confirmed"
    assert row.cancellation_reason is None  # rejected cancel leaves the field untouched


def test_cancel_completed_booking_400(client, customer_headers, admin_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    confirmed = confirm_booking(client, customer_headers, created)
    done = client.patch(
        f"/admin/bookings/{confirmed['id']}",
        headers=admin_headers,
        json={"action": "complete"},
    )
    assert done.status_code == 200
    resp = client.post(
        f"/bookings/{confirmed['id']}/cancel", headers=customer_headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_status"
