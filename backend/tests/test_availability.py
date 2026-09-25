"""Phase 2 — availability engine: grid, hours, duration, overlaps, past, expiry."""

from datetime import timedelta

from app.core.timeutil import utcnow
from app.db import SessionLocal
from app.models import Booking
from tests.conftest import create_booking, service_ids, slot_utc, future_day


def slots_by_start(resp_json) -> dict[str, bool]:
    return {s["start_at"]: s["available"] for s in resp_json["slots"]}


def test_grid_first_and_last_slot_haircut(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["barber_id"] == 1
    assert body["date"] == day.isoformat()
    assert body["duration_minutes"] == 60

    # Mon–Sat 09:00–20:00 IST; start+60 <= 20:00 → last start 19:00 IST.
    first = slot_utc(day, 9, 0).isoformat().replace("+00:00", "Z")
    last = slot_utc(day, 19, 0).isoformat().replace("+00:00", "Z")
    starts = [s["start_at"] for s in body["slots"]]
    assert starts[0] == first
    assert starts[-1] == last
    # 09:00..19:00 inclusive step 15 → 41 slots
    assert len(starts) == 41
    assert all(s["available"] is True for s in body["slots"])

    # 15-minute grid: differences are multiples of 15 min
    from datetime import datetime

    parsed = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in starts]
    for a, b in zip(parsed, parsed[1:]):
        assert b - a == timedelta(minutes=15)


def test_duration_filters_last_start(client, customer_headers):
    day = future_day()
    ids = service_ids(client)

    # Full combo 120 min → last start 18:00 IST
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": ids["Full combo"]},
    )
    starts = [s["start_at"] for s in resp.json()["slots"]]
    assert starts[-1] == slot_utc(day, 18, 0).isoformat().replace("+00:00", "Z")
    assert len(starts) == 37  # 09:00..18:00 step 15

    # Haircut + wash = 75 min → last start 18:45 IST
    resp = client.get(
        "/barbers/1/availability",
        params={
            "date": day.isoformat(),
            "service_id": ids["Haircut"],
            "addons": "wash",
        },
    )
    body = resp.json()
    assert body["duration_minutes"] == 75
    starts = [s["start_at"] for s in body["slots"]]
    assert starts[-1] == slot_utc(day, 18, 45).isoformat().replace("+00:00", "Z")
    assert len(starts) == 40


def test_confirmed_booking_blocks_overlapping_slots(
    client, customer_headers, admin_headers
):
    day = future_day()
    sid = service_ids(client)["Haircut"]

    booking = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=10
    )
    # hold is active → blocks immediately
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    starts = [s["start_at"] for s in resp.json()["slots"]]
    z = lambda h, m=0: slot_utc(day, h, m).isoformat().replace("+00:00", "Z")

    assert z(9, 0) in starts       # ends exactly when hold starts → free
    assert z(9, 15) not in starts  # overlaps [10:00,11:00)
    assert z(10, 0) not in starts
    assert z(10, 45) not in starts
    assert z(11, 0) in starts      # starts when hold ends → free

    # confirm it — still blocked
    from tests.conftest import confirm_booking

    confirm_booking(client, customer_headers, booking)
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    starts2 = [s["start_at"] for s in resp.json()["slots"]]
    assert z(10, 0) not in starts2


def test_expired_hold_frees_slot_and_blocks_verify(
    client, customer_headers, db, fake_payments
):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    booking = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=10
    )
    bid = booking["booking"]["id"]

    # simulate the 12-minute hold lapsing
    row = db.get(Booking, __import__("uuid").UUID(bid))
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    # slot available again
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    starts = [s["start_at"] for s in resp.json()["slots"]]
    z = slot_utc(day, 10, 0).isoformat().replace("+00:00", "Z")
    assert z in starts

    # but the payment can no longer confirm the hold
    resp = client.post(
        f"/bookings/{bid}/verify-payment",
        headers=customer_headers,
        json={
            "razorpay_order_id": booking["payment"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_late",
            "razorpay_signature": "sig",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "hold_expired"

    db.expire_all()
    assert db.get(Booking, __import__("uuid").UUID(bid)).status == "pending_payment"


def test_past_slots_excluded_for_today(client):
    from app.core.timeutil import kolkata_date

    today = kolkata_date(utcnow())
    sid = service_ids(client)["Haircut"]
    resp = client.get(
        "/barbers/1/availability",
        params={"date": today.isoformat(), "service_id": sid},
    )
    assert resp.status_code == 200
    now = utcnow()
    parsed = [
        __import__("datetime").datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
        for s in resp.json()["slots"]
    ]
    assert all(p > now for p in parsed)


def test_closed_day_returns_no_slots(client, admin_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]

    # close that weekday via admin schedule PUT
    schedule = client.get("/admin/barbers/1/schedule", headers=admin_headers).json()
    target_weekday = day.weekday()
    payload = [
        {
            "weekday": row["weekday"],
            "open_time": row["open_time"],
            "close_time": row["close_time"],
            "is_closed": row["weekday"] == target_weekday,
        }
        for row in schedule
    ]
    assert client.put(
        "/admin/barbers/1/schedule", headers=admin_headers, json=payload
    ).status_code == 200

    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    assert resp.json()["slots"] == []


def test_availability_validation(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]

    # missing service_id → 422
    assert (
        client.get("/barbers/1/availability", params={"date": day.isoformat()}).status_code
        == 422
    )
    # unknown service → 404
    assert (
        client.get(
            "/barbers/1/availability",
            params={"date": day.isoformat(), "service_id": 9999},
        ).status_code
        == 404
    )
    # unknown barber → 404
    assert (
        client.get(
            "/barbers/99/availability",
            params={"date": day.isoformat(), "service_id": sid},
        ).status_code
        == 404
    )
    # unknown addon → 400
    resp = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": sid, "addons": "nope"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown_addon"


def test_other_barber_slots_unaffected_by_overlap(client, customer_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    create_booking(
        client, customer_headers, service_id=sid, barber_id=1, day=day, hour=10
    )
    resp = client.get(
        "/barbers/2/availability",
        params={"date": day.isoformat(), "service_id": sid},
    )
    starts = [s["start_at"] for s in resp.json()["slots"]]
    z = slot_utc(day, 10, 0).isoformat().replace("+00:00", "Z")
    assert z in starts  # different barber unaffected
