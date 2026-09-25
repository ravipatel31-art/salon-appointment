"""Phase 6 — end-to-end journeys across the full API surface.

Journeys covered (contract order):
  register → services/barbers → availability → booking (hold) →
  mock pay → verify-payment → confirmed → admin complete / cancel+refund →
  dashboard.

Uses the *real* ``payments.py`` behind ``RAZORPAY_MOCK=1`` (``real_payments``
fixture) so order ids and HMAC signatures exercise the integration code path,
not the conftest FakePayments stand-in.
"""

from __future__ import annotations

from tests.conftest import (  # noqa: F401 — helpers
    CUSTOMER1,
    future_day,
    service_ids,
    slot_utc,
)
from tests.test_payment_fixtures import (  # noqa: F401 — fixtures resolved via module namespace
    payment_captured_event,
    post_webhook,
    real_payments,
    sign_payment,
)


def _register(client, payload: dict | None = None) -> tuple[dict, dict]:
    """Register a customer → (access_token_json_headers, user_dict)."""
    body = payload or CUSTOMER1
    resp = client.post("/auth/register", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return headers, data["user"]


def test_e2e_full_journey_register_to_dashboard(client, real_payments, admin_headers):
    # 1) register ---------------------------------------------------------
    headers, user = _register(
        client,
        {
            "name": "E2E Journey",
            "phone": "+919811100001",
            "email": "e2e-journey@example.com",
            "password": "secret-123",
        },
    )
    assert user["role"] == "customer"
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["user"]["id"] == user["id"]

    # 2) catalog ----------------------------------------------------------
    services = client.get("/services").json()["items"]
    names = {s["name"] for s in services}
    assert {"Haircut", "Beard trim", "Hair color"} <= names
    haircut = next(s for s in services if s["name"] == "Haircut")
    assert haircut["price"] == 100 and haircut["price_type"] == "fixed"
    assert {"id": "wash", "name": "Wash", "price": 30, "duration_minutes": 15} in haircut["addons"]

    barbers = client.get("/barbers").json()["items"]
    assert len(barbers) == 5 and all(b["is_active"] for b in barbers)

    # 3) availability -----------------------------------------------------
    day = future_day()
    avail = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": haircut["id"], "addons": "wash"},
    )
    assert avail.status_code == 200
    slots = avail.json()["slots"]
    assert avail.json()["duration_minutes"] == 75  # 60 + wash 15
    target = slot_utc(day, 10, 0).isoformat().replace("+00:00", "Z")
    assert {"start_at": target, "available": True} in slots

    # 4) booking → pending_payment hold + payment object ------------------
    resp = client.post(
        "/bookings",
        headers=headers,
        json={
            "service_id": haircut["id"],
            "addons": ["wash"],
            "barber_id": 1,
            "start_at": target,
            "notes": "e2e journey",
        },
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()["booking"]
    payment = resp.json()["payment"]
    assert booking["status"] == "pending_payment"
    assert booking["booking_ref"].startswith(f"SL-{day.strftime('%Y%m%d')}-")
    assert booking["total_amount"] == 130 and booking["advance_amount"] == 65
    assert booking["balance_amount"] == 65 and booking["online_amount_paid"] == 0
    assert booking["duration_minutes"] == 75
    assert payment["razorpay_amount"] == 6500  # paise = ₹65 × 100
    assert payment["razorpay_currency"] == "INR"
    assert payment["razorpay_order_id"].startswith("order_mock_")  # real create_order, mock gateway
    assert payment["key_id"]

    # active hold hides the slot from availability
    avail2 = client.get(
        "/barbers/1/availability",
        params={"date": day.isoformat(), "service_id": haircut["id"], "addons": "wash"},
    )
    assert target not in [s["start_at"] for s in avail2.json()["slots"]]

    # 5) mock pay → verify-payment (real HMAC) → confirmed ----------------
    pay_id = "pay_e2e_journey_1"
    sig = sign_payment(payment["razorpay_order_id"], pay_id)
    resp = client.post(
        f"/bookings/{booking['id']}/verify-payment",
        headers=headers,
        json={
            "razorpay_order_id": payment["razorpay_order_id"],
            "razorpay_payment_id": pay_id,
            "razorpay_signature": sig,
        },
    )
    assert resp.status_code == 200, resp.text
    confirmed = resp.json()["booking"]
    assert confirmed["status"] == "confirmed"
    assert confirmed["online_amount_paid"] == 65 == confirmed["advance_amount"]
    assert confirmed["service_name"] == "Haircut" and confirmed["barber_name"]

    # Mock bypass (contract 2026-09-24) accepts any non-empty triple under
    # RAZORPAY_MOCK=1 — but a whitespace-only signature still fails after strip
    # (schema min_length=1 admits it). HMAC enforcement on the real path is
    # covered by the non-mock unit tests in test_payment_service.py.
    other_headers, _ = _register(
        client,
        {
            "name": "Twin Customer",
            "phone": "+919811100002",
            "email": "e2e-twin@example.com",
            "password": "secret-123",
        },
    )
    twin = client.post(
        "/bookings",
        headers=other_headers,
        json={
            "service_id": haircut["id"],
            "addons": [],
            "barber_id": 3,
            "start_at": slot_utc(day, 10, 0).isoformat().replace("+00:00", "Z"),
            "notes": "",
        },
    )
    assert twin.status_code == 201
    bad = client.post(
        f"/bookings/{twin.json()['booking']['id']}/verify-payment",
        headers=other_headers,
        json={
            "razorpay_order_id": twin.json()["payment"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "   ",  # empty after strip → mock bypass rejects
        },
    )
    assert bad.status_code == 400 and bad.json()["detail"] == "verification_failed"

    # 6) admin list filters + complete ------------------------------------
    resp = client.get(
        "/admin/bookings",
        params={"date": day.isoformat(), "status": "confirmed"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["items"]] == [booking["id"]]

    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete"},
    )
    assert resp.status_code == 200
    done = resp.json()["booking"]
    assert done["status"] == "completed"
    assert done["final_price_at_center"] == 130  # fixed service → total
    assert done["balance_due"] == 130 - 65

    # customer GET reflects completion
    got = client.get(f"/bookings/{booking['id']}", headers=headers).json()
    assert got["status"] == "completed"
    assert got["balance_due"] == 65

    # 7) dashboard --------------------------------------------------------
    resp = client.get(
        "/admin/dashboard", params={"date": day.isoformat()}, headers=admin_headers
    )
    assert resp.status_code == 200
    dash = resp.json()
    assert dash["date"] == day.isoformat()
    # A completed (130/65) + B still pending_payment hold (never paid)
    assert dash["bookings_count"] == 2  # both active (neither cancelled/refunded)
    assert dash["confirmed_count"] == 0  # A completed; B still pending
    assert dash["revenue_online"] == 65  # only A captured online
    assert dash["revenue_at_center"] == 65  # A balance_due


def test_e2e_pay_confirm_cancel_refund(client, real_payments, admin_headers):
    """cancel ≥2h before start → real mock refund → booking ends ``refunded``."""
    headers, _ = _register(
        client,
        {
            "name": "Refund Customer",
            "phone": "+919811100003",
            "email": "e2e-refund@example.com",
            "password": "secret-123",
        },
    )
    day = future_day()
    sid = service_ids(client)["Haircut"]
    target = slot_utc(day, 11, 0).isoformat().replace("+00:00", "Z")

    created = client.post(
        "/bookings",
        headers=headers,
        json={"service_id": sid, "addons": [], "barber_id": 2, "start_at": target, "notes": ""},
    )
    assert created.status_code == 201, created.text
    booking = created.json()["booking"]
    payment = created.json()["payment"]

    pay_id = "pay_e2e_refund_1"
    resp = client.post(
        f"/bookings/{booking['id']}/verify-payment",
        headers=headers,
        json={
            "razorpay_order_id": payment["razorpay_order_id"],
            "razorpay_payment_id": pay_id,
            "razorpay_signature": sign_payment(payment["razorpay_order_id"], pay_id),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["booking"]["status"] == "confirmed"
    assert resp.json()["booking"]["online_amount_paid"] == 50

    # cancel ≥2h ahead (future_day is ~2 weeks out) → refund of ₹50 advance
    resp = client.post(f"/bookings/{booking['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    # Route builds its payload before the synchronous mock refund marks the row;
    # the durable state after the request is what matters.
    assert resp.json()["booking"]["status"] in ("cancelled", "refunded")

    final = client.get(f"/bookings/{booking['id']}", headers=headers).json()
    assert final["status"] == "refunded"  # real payments.refund → attempt_refund_mark

    # second cancel rejected (terminal state)
    again = client.post(f"/bookings/{booking['id']}/cancel", headers=headers)
    assert again.status_code == 400 and again.json()["detail"] == "invalid_status"

    # refunded booking drops out of dashboard revenue/counts
    dash = client.get(
        "/admin/dashboard", params={"date": day.isoformat()}, headers=admin_headers
    ).json()
    assert dash["bookings_count"] == 0
    assert dash["confirmed_count"] == 0
    assert dash["revenue_online"] == 0
    assert dash["revenue_at_center"] == 0


def test_e2e_webhook_confirm_replay_and_bad_signature(client, real_payments):
    """POST /webhooks/razorpay wired in main app: 401 → confirm → idempotent replay."""
    headers, _ = _register(
        client,
        {
            "name": "Webhook Customer",
            "phone": "+919811100004",
            "email": "e2e-webhook@example.com",
            "password": "secret-123",
        },
    )
    day = future_day()
    sid = service_ids(client)["Haircut"]
    target = slot_utc(day, 14, 0).isoformat().replace("+00:00", "Z")

    created = client.post(
        "/bookings",
        headers=headers,
        json={"service_id": sid, "addons": [], "barber_id": 4, "start_at": target, "notes": ""},
    )
    assert created.status_code == 201, created.text
    booking = created.json()["booking"]
    order_id = created.json()["payment"]["razorpay_order_id"]
    pay_id = "pay_e2e_webhook_1"
    body = payment_captured_event(order_id=order_id, payment_id=pay_id, amount_paise=5000)

    # bad signature first — must not confirm
    resp = post_webhook(client, body, signature="0" * 64)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_signature"
    assert client.get(f"/bookings/{booking['id']}", headers=headers).json()["status"] == "pending_payment"

    # valid signature → confirmed
    resp = post_webhook(client, body)
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "confirmed"
    assert resp.json()["razorpay_payment_id"] == pay_id
    after = client.get(f"/bookings/{booking['id']}", headers=headers).json()
    assert after["status"] == "confirmed"
    assert after["online_amount_paid"] == 50  # advance from booking row, not raw amount

    # replay of the same payment id → idempotent no-op
    replay = post_webhook(client, body)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "already_processed"
    after2 = client.get(f"/bookings/{booking['id']}", headers=headers).json()
    assert after2["status"] == "confirmed"
    assert after2["online_amount_paid"] == 50  # never double-set
