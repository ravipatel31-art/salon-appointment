"""Phase 3 unit tests — payments service contract, signatures, gateway calls."""

from __future__ import annotations

import inspect

import pytest

from app.services import payments
from tests.test_payment_fixtures import (
    BookingStore,
    booking_store,  # noqa: F401 — pytest fixture (imported into module namespace)
    razorpay_env,
    razorpay_mock_env,
    sign_payment,
)


# ---------------------------------------------------------------------------
# Frozen contract interface
# ---------------------------------------------------------------------------


def test_contract_signatures_are_exact() -> None:
    create_order = inspect.signature(payments.create_order)
    assert list(create_order.parameters) == ["amount_rupees", "receipt"]

    verify_payment = inspect.signature(payments.verify_payment)
    assert list(verify_payment.parameters) == ["order_id", "payment_id", "signature"]

    refund = inspect.signature(payments.refund)
    assert list(refund.parameters) == ["payment_id", "amount_rupees"]
    assert refund.parameters["amount_rupees"].default is None

    verify_webhook = inspect.signature(payments.verify_webhook)
    assert list(verify_webhook.parameters) == ["body", "signature"]


# ---------------------------------------------------------------------------
# create_order — rupees → paise ×100
# ---------------------------------------------------------------------------


def test_create_order_converts_rupees_to_paise(monkeypatch: pytest.MonkeyPatch, razorpay_env) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, path: str, json_body: dict | None = None) -> dict:
        calls.append((method, path, json_body))
        return {"id": "order_abc123", "status": "created", "amount": json_body["amount"]}

    monkeypatch.setattr(payments, "_razorpay_request", fake_request)

    result = payments.create_order(65, "SL-20260924-0042")

    assert calls == [
        ("POST", "/orders", {"amount": 6500, "currency": "INR", "receipt": "SL-20260924-0042"})
    ]
    # Contract payment-object keys
    assert result["razorpay_order_id"] == "order_abc123"
    assert result["razorpay_amount"] == 6500
    assert result["razorpay_currency"] == "INR"
    assert result["key_id"] == "rzp_test_key"
    # Raw aliases
    assert result["id"] == "order_abc123"
    assert result["amount"] == 6500


def test_create_order_mock_mode_never_hits_network(
    monkeypatch: pytest.MonkeyPatch, razorpay_mock_env
) -> None:
    def forbid(*args, **kwargs):  # pragma: no cover
        raise AssertionError("gateway HTTP must not be called in mock mode")

    monkeypatch.setattr(payments, "_razorpay_request", forbid)

    result = payments.create_order(100, "SL-20260924-0007")

    assert result["razorpay_order_id"].startswith("order_mock_")
    assert result["razorpay_amount"] == 10000  # ₹100 → 10000 paise
    assert result["key_id"]


def test_create_order_rejects_invalid_amounts(razorpay_env) -> None:
    with pytest.raises(ValueError):
        payments.create_order(0, "SL-1")
    with pytest.raises(ValueError):
        payments.create_order(-5, "SL-1")
    with pytest.raises(ValueError):
        payments.create_order(65, "   ")


def test_create_order_requires_gateway_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import payments as p

    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    monkeypatch.setenv("RAZORPAY_MOCK", "0")
    p.get_razorpay_settings.cache_clear()
    try:
        with pytest.raises(p.PaymentsError):
            p.create_order(65, "SL-1")
    finally:
        p.get_razorpay_settings.cache_clear()


# ---------------------------------------------------------------------------
# verify_payment — HMAC-SHA256(order_id|payment_id)
# ---------------------------------------------------------------------------


def test_verify_payment_accepts_valid_signature(razorpay_env) -> None:
    signature = sign_payment("order_1", "pay_1")
    assert payments.verify_payment("order_1", "pay_1", signature) is True


def test_verify_payment_rejects_tampered_signature(razorpay_env) -> None:
    signature = sign_payment("order_1", "pay_1")
    assert payments.verify_payment("order_1", "pay_2", signature) is False  # wrong payment
    assert payments.verify_payment("order_2", "pay_1", signature) is False  # wrong order
    assert payments.verify_payment("order_1", "pay_1", signature[:-2] + "00") is False
    assert payments.verify_payment("order_1", "pay_1", "") is False


def test_verify_payment_fails_closed_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    monkeypatch.setenv("RAZORPAY_MOCK", "0")  # pin the non-mock HMAC path
    payments.get_razorpay_settings.cache_clear()
    try:
        assert payments.verify_payment("order_1", "pay_1", "any") is False
    finally:
        payments.get_razorpay_settings.cache_clear()


# ---------------------------------------------------------------------------
# verify_payment — mock bypass (CONTRACT_CHANGE 2026-09-24, local/demo only)
# ---------------------------------------------------------------------------


def test_verify_payment_mock_accepts_non_empty_triple(razorpay_mock_env) -> None:
    """RAZORPAY_MOCK=1 → any non-empty order/payment/signature verifies (no HMAC)."""
    assert payments.get_razorpay_settings().razorpay_mock is True
    # Not a valid HMAC — accepted only because the test bypass is on.
    assert payments.verify_payment("order_mock_SL1", "pay_MOCK1", "sig_MOCK1") is True
    # Arbitrary strings work too (Flutter MockPaymentGateway emits pay_MOCK*/sig_MOCK*).
    assert payments.verify_payment("order_x", "pay_x", "deadbeef" * 8) is True
    # Non-empty after strip counts as non-empty.
    assert payments.verify_payment(" order_1 ", " pay_1 ", " sig ") is True


def test_verify_payment_mock_rejects_empty_signature(razorpay_mock_env) -> None:
    """Bypass still fails closed on any empty / whitespace-only part."""
    assert payments.verify_payment("order_1", "pay_1", "") is False
    assert payments.verify_payment("order_1", "pay_1", "   ") is False
    assert payments.verify_payment("", "pay_1", "sig") is False
    assert payments.verify_payment("  ", "pay_1", "sig") is False
    assert payments.verify_payment("order_1", "", "sig") is False
    assert payments.verify_payment("order_1", "  ", "sig") is False


def test_verify_payment_mock_bypass_skips_hmac_even_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock verify never consults RAZORPAY_KEY_SECRET (pure non-empty check)."""
    monkeypatch.setenv("RAZORPAY_MOCK", "1")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    payments.get_razorpay_settings.cache_clear()
    try:
        assert payments.verify_payment("o", "p", "s") is True
        assert payments.verify_payment("o", "p", "") is False
    finally:
        payments.get_razorpay_settings.cache_clear()


def test_verify_payment_non_mock_still_enforces_hmac(razorpay_env) -> None:
    """With RAZORPAY_MOCK=0 the mock-style triple must NOT bypass HMAC."""
    assert payments.get_razorpay_settings().razorpay_mock is False
    assert payments.verify_payment("order_mock_SL1", "pay_MOCK1", "sig_MOCK1") is False
    assert payments.verify_payment("order_1", "pay_1", "deadbeef" * 8) is False


# ---------------------------------------------------------------------------
# verify_webhook — HMAC-SHA256(raw body)
# ---------------------------------------------------------------------------


def test_verify_webhook_accepts_valid_signature(razorpay_env) -> None:
    from tests.test_payment_fixtures import sign_webhook

    body = b'{"event":"payment.captured"}'
    assert payments.verify_webhook(body, sign_webhook(body)) is True


def test_verify_webhook_rejects_invalid_signature(razorpay_env) -> None:
    body = b'{"event":"payment.captured"}'
    assert payments.verify_webhook(body, "a" * 64) is False
    assert payments.verify_webhook(body, "") is False
    assert payments.verify_webhook(b"", "a" * 64) is False


def test_verify_webhook_fails_closed_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "")
    payments.get_razorpay_settings.cache_clear()
    try:
        assert payments.verify_webhook(b"{}", "sig") is False
    finally:
        payments.get_razorpay_settings.cache_clear()


# ---------------------------------------------------------------------------
# refund — paise conversion + booking mark
# ---------------------------------------------------------------------------


def test_refund_converts_rupees_to_paise_and_uses_payment_path(
    monkeypatch: pytest.MonkeyPatch, razorpay_env
) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, path: str, json_body: dict | None = None) -> dict:
        calls.append((method, path, json_body))
        return {"id": "rfnd_abc", "status": "processed", "amount": 6500}

    monkeypatch.setattr(payments, "_razorpay_request", fake_request)

    result = payments.refund("pay_1", 65)

    assert calls == [("POST", "/payments/pay_1/refund", {"amount": 6500})]
    assert result["razorpay_refund_id"] == "rfnd_abc"
    assert result["payment_id"] == "pay_1"
    assert result["status"] == "processed"
    assert result["amount"] == 6500


def test_refund_full_amount_when_none(
    monkeypatch: pytest.MonkeyPatch, razorpay_env
) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, path: str, json_body: dict | None = None) -> dict:
        calls.append((method, path, json_body))
        return {"id": "rfnd_full", "status": "processed"}

    monkeypatch.setattr(payments, "_razorpay_request", fake_request)
    payments.refund("pay_2")
    assert calls == [("POST", "/payments/pay_2/refund", None)]


def test_refund_mock_mode_returns_processed(monkeypatch: pytest.MonkeyPatch, razorpay_mock_env) -> None:
    def forbid(*args, **kwargs):  # pragma: no cover
        raise AssertionError("gateway HTTP must not be called in mock mode")

    monkeypatch.setattr(payments, "_razorpay_request", forbid)
    result = payments.refund("pay_3", 50)
    assert result["status"] == "processed"
    assert result["razorpay_refund_id"].startswith("rfnd_mock_")


def test_refund_marks_cancelled_booking_refunded(
    monkeypatch: pytest.MonkeyPatch, razorpay_mock_env, booking_store: BookingStore
) -> None:
    import app.db as app_db

    # refund()'s best-effort mark opens its own session — point it at sqlite.
    monkeypatch.setattr(app_db, "SessionLocal", booking_store.Session)

    booking_id = booking_store.add(
        status="cancelled",
        razorpay_payment_id="pay_cancel_1",
        online_amount_paid=65,
    )

    payments.refund("pay_cancel_1", 65)

    row = booking_store.get(booking_id)
    assert row is not None
    assert row["status"] == "refunded"


def test_refund_api_error_propagates(
    monkeypatch: pytest.MonkeyPatch, razorpay_env
) -> None:
    def boom(*args, **kwargs):
        raise payments.PaymentsError("gateway down")

    monkeypatch.setattr(payments, "_razorpay_request", boom)
    with pytest.raises(payments.PaymentsError):
        payments.refund("pay_err")


def test_refund_requires_payment_id(razorpay_env) -> None:
    with pytest.raises(ValueError):
        payments.refund("")
