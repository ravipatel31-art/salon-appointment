"""Phase 3 webhook tests — signature failure, confirm, replay idempotency, refunds."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from tests.test_payment_fixtures import (
    BookingStore,
    booking_store,  # noqa: F401 — pytest fixture
    now_utc,
    payment_captured_event,
    post_webhook,
    razorpay_env,
    razorpay_mock_env,
    refund_processed_event,
    sign_webhook,
    webhook_app,  # noqa: F401 — pytest fixture
    webhook_client,  # noqa: F401 — pytest fixture
)

ADVANCE_PAISE = 6500  # ₹65 advance


def test_webhook_rejects_invalid_signature(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    booking_id = booking_store.add(razorpay_order_id="order_x1")
    body = payment_captured_event(order_id="order_x1", payment_id="pay_x1", amount_paise=ADVANCE_PAISE)

    resp = post_webhook(webhook_client, body, signature="f" * 64)

    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_signature"
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "pending_payment"


def test_webhook_rejects_signed_body_tamper(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    """Signature over different bytes must fail (raw-body check)."""
    booking_id = booking_store.add(razorpay_order_id="order_x2")
    good_body = payment_captured_event(order_id="order_x2", payment_id="pay_x2", amount_paise=ADVANCE_PAISE)
    sig = sign_webhook(good_body)

    evil_body = payment_captured_event(order_id="order_x2", payment_id="pay_EVIL", amount_paise=1)

    resp = post_webhook(webhook_client, evil_body, signature=sig)
    assert resp.status_code == 401
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "pending_payment"


def test_webhook_confirms_pending_booking(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    booking_id = booking_store.add(razorpay_order_id="order_ok", advance_amount=65)
    body = payment_captured_event(order_id="order_ok", payment_id="pay_ok", amount_paise=ADVANCE_PAISE)

    resp = post_webhook(webhook_client, body)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "confirmed"
    row = booking_store.get(booking_id)
    assert row is not None
    assert row["status"] == "confirmed"
    assert row["online_amount_paid"] == 65  # advance in rupees
    assert row["razorpay_payment_id"] == "pay_ok"


def test_webhook_replay_is_idempotent(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    """Same razorpay_payment_id delivered twice → single confirm, second is a no-op."""
    booking_id = booking_store.add(razorpay_order_id="order_r1", advance_amount=65)
    body = payment_captured_event(order_id="order_r1", payment_id="pay_r1", amount_paise=ADVANCE_PAISE)

    first = post_webhook(webhook_client, body)
    second = post_webhook(webhook_client, body)
    third = post_webhook(webhook_client, body)

    assert first.status_code == 200 and first.json()["outcome"] == "confirmed"
    for replay in (second, third):
        assert replay.status_code == 200
        assert replay.json()["outcome"] == "already_processed"
        assert replay.json()["razorpay_payment_id"] == "pay_r1"

    row = booking_store.get(booking_id)
    assert row is not None
    assert row["status"] == "confirmed"
    assert row["online_amount_paid"] == 65  # never double-set


def test_webhook_does_not_confirm_expired_hold(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    booking_id = booking_store.add(
        razorpay_order_id="order_exp",
        expires_at=now_utc() - timedelta(minutes=1),
    )
    body = payment_captured_event(order_id="order_exp", payment_id="pay_exp", amount_paise=ADVANCE_PAISE)

    resp = post_webhook(webhook_client, body)

    assert resp.status_code == 200
    # sweep ran first → hold was cancelled; confirm then reports hold_expired
    assert resp.json()["outcome"] in {"hold_expired", "ignored"}
    row = booking_store.get(booking_id)
    assert row is not None
    assert row["status"] in {"cancelled", "pending_payment"}
    assert row["status"] != "confirmed"


def test_webhook_unknown_order_is_ignored(webhook_client: TestClient, razorpay_env) -> None:
    body = payment_captured_event(order_id="order_missing", payment_id="pay_missing", amount_paise=ADVANCE_PAISE)
    resp = post_webhook(webhook_client, body)
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "booking_not_found"


def test_webhook_payment_failed_does_not_confirm(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    booking_id = booking_store.add(razorpay_order_id="order_fail")
    body = payment_captured_event(
        order_id="order_fail", payment_id="pay_fail", amount_paise=ADVANCE_PAISE, event="payment.failed"
    )

    resp = post_webhook(webhook_client, body)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "ignored"
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "pending_payment"


def test_webhook_refund_marks_cancelled_booking_refunded(
    webhook_client: TestClient, booking_store: BookingStore, razorpay_env
) -> None:
    booking_id = booking_store.add(
        razorpay_order_id="order_ref",
        razorpay_payment_id="pay_ref",
        status="cancelled",
        online_amount_paid=65,
    )
    body = refund_processed_event(payment_id="pay_ref", order_id="order_ref", amount_paise=ADVANCE_PAISE)

    resp = post_webhook(webhook_client, body)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "refunded"
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "refunded"


def test_webhook_refund_replay_idempotent(webhook_client: TestClient, booking_store: BookingStore, razorpay_env) -> None:
    booking_id = booking_store.add(
        razorpay_order_id="order_ref2",
        razorpay_payment_id="pay_ref2",
        status="cancelled",
    )
    body = refund_processed_event(payment_id="pay_ref2", order_id="order_ref2", amount_paise=ADVANCE_PAISE)

    first = post_webhook(webhook_client, body)
    second = post_webhook(webhook_client, body)

    assert first.json()["outcome"] == "refunded"
    assert second.status_code == 200
    assert second.json()["outcome"] == "already_processed"
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "refunded"


def test_webhook_refund_ignored_when_not_cancelled(
    webhook_client: TestClient, booking_store: BookingStore, razorpay_env
) -> None:
    booking_id = booking_store.add(
        razorpay_order_id="order_ref3",
        razorpay_payment_id="pay_ref3",
        status="confirmed",
    )
    body = refund_processed_event(payment_id="pay_ref3", order_id="order_ref3", amount_paise=ADVANCE_PAISE)

    resp = post_webhook(webhook_client, body)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "ignored"
    row = booking_store.get(booking_id)
    assert row is not None and row["status"] == "confirmed"


def test_webhook_rejects_validly_signed_invalid_json(webhook_client: TestClient, razorpay_env) -> None:
    """Signature passes (raw bytes signed) but body is not JSON → 400."""
    body = b"not-json{"
    resp = post_webhook(webhook_client, body)  # signs the raw bytes correctly
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_payload"
