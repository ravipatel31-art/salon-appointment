"""Phase 6 — refund path hardening through the real payments module.

Covers: cancel ≥2h → refund(advance in rupees); gateway failure leaves the
booking ``cancelled`` until the durable ``refund.processed`` webhook backstop
flips it to ``refunded``; idempotent terminal states.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session  # noqa: F401 — typing hint for db fixture

from app.services import payment_interface
from tests.conftest import (  # noqa: F401 — helpers
    create_booking,
    future_day,
    service_ids,
    slot_utc,
)
from tests.test_payment_fixtures import (  # noqa: F401 — fixtures via namespace
    post_webhook,
    real_payments,
    refund_processed_event,
    sign_payment,
)


def _confirmed_hold(client, headers, *, day, hour: int, barber_id: int = 1) -> tuple[dict, dict, str]:
    """Create + verify a Haircut hold via the real mock gateway.

    Returns (booking_dict, payment_dict, payment_id).
    """
    sid = service_ids(client)["Haircut"]
    created = client.post(
        "/bookings",
        headers=headers,
        json={
            "service_id": sid,
            "addons": [],
            "barber_id": barber_id,
            "start_at": slot_utc(day, hour, 0).isoformat().replace("+00:00", "Z"),
            "notes": "",
        },
    )
    assert created.status_code == 201, created.text
    booking = created.json()["booking"]
    payment = created.json()["payment"]
    pay_id = f"pay_refund_path_{booking['booking_ref']}"
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
    return resp.json()["booking"], payment, pay_id


def test_cancel_invokes_refund_with_advance_rupees_and_marks_refunded(
    client, customer_headers, real_payments, monkeypatch: pytest.MonkeyPatch
):
    day = future_day()
    booking, _payment, pay_id = _confirmed_hold(
        client, customer_headers, day=day, hour=10
    )
    assert booking["online_amount_paid"] == 50  # ₹100 haircut → 50% advance

    calls: list[tuple[str, int | None]] = []
    real_refund = real_payments.refund  # real module (mock gateway)

    def spy_refund(payment_id: str, amount_rupees: int | None = None) -> dict:
        calls.append((payment_id, amount_rupees))
        return real_refund(payment_id, amount_rupees)

    monkeypatch.setattr(payment_interface, "refund", spy_refund)

    resp = client.post(f"/bookings/{booking['id']}/cancel", headers=customer_headers)
    assert resp.status_code == 200, resp.text

    # Cancel enqueued the refund with the payment id + advance in rupees.
    assert calls == [(pay_id, 50)]

    # Real mock refund performed the cancelled → refunded mark.
    final = client.get(f"/bookings/{booking['id']}", headers=customer_headers).json()
    assert final["status"] == "refunded"


def test_refund_gateway_error_leaves_cancelled_until_webhook_backstop(
    client, customer_headers, real_payments, monkeypatch: pytest.MonkeyPatch
):
    """Gateway down during cancel → stays cancelled; refund.processed recovers."""
    day = future_day()
    booking, payment, pay_id = _confirmed_hold(
        client, customer_headers, day=day, hour=12
    )

    def boom(payment_id: str, amount_rupees: int | None = None) -> dict:
        raise real_payments.PaymentsError("gateway down")

    monkeypatch.setattr(payment_interface, "refund", boom)

    # Cancel still succeeds (route swallows refund enqueue errors).
    resp = client.post(f"/bookings/{booking['id']}/cancel", headers=customer_headers)
    assert resp.status_code == 200, resp.text

    state = client.get(f"/bookings/{booking['id']}", headers=customer_headers).json()
    assert state["status"] == "cancelled"  # not refunded yet — advance still out

    # Razorpay delivers refund.processed later → idempotent backstop.
    body = refund_processed_event(
        payment_id=pay_id,
        order_id=payment["razorpay_order_id"],
        amount_paise=5000,
        refund_id="rfnd_e2e_backstop",
    )
    resp = post_webhook(client, body)
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "refunded"

    state = client.get(f"/bookings/{booking['id']}", headers=customer_headers).json()
    assert state["status"] == "refunded"

    # Webhook replay stays idempotent.
    replay = post_webhook(client, body)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "already_processed"
    state = client.get(f"/bookings/{booking['id']}", headers=customer_headers).json()
    assert state["status"] == "refunded"


def test_unpaid_hold_cancel_skips_refund_on_real_path(
    client, customer_headers, real_payments, monkeypatch: pytest.MonkeyPatch
):
    """No money captured → cancel must not call the gateway refund."""
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(
        client, customer_headers, service_id=sid, day=day, hour=15
    )
    bid = created["booking"]["id"]

    calls: list[tuple] = []

    def spy_refund(payment_id: str, amount_rupees: int | None = None) -> dict:
        calls.append((payment_id, amount_rupees))
        return real_payments.refund(payment_id, amount_rupees)

    monkeypatch.setattr(payment_interface, "refund", spy_refund)

    resp = client.post(f"/bookings/{bid}/cancel", headers=customer_headers)
    assert resp.status_code == 200
    assert resp.json()["booking"]["status"] == "cancelled"
    assert calls == []  # online_amount_paid == 0 → nothing to refund

    final = client.get(f"/bookings/{bid}", headers=customer_headers).json()
    assert final["status"] == "cancelled"  # stays cancelled, never refunded
