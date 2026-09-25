"""Delegate to salon-integration's ``app/services/payments.py`` (contract interface).

Contract (docs/CONTRACT.md):

    def create_order(amount_rupees: int, receipt: str) -> dict: ...
    def verify_payment(order_id: str, payment_id: str, signature: str) -> bool: ...
    def refund(payment_id: str, amount_rupees: int | None = None) -> dict: ...
    def verify_webhook(body: bytes, signature: str) -> bool: ...

This module is owned by salon-backend. It never edits ``payments.py``; if that
module does not exist yet (integration still pending), safe local fallbacks keep
the booking APIs working. All route code calls *this* module, so tests can
monkeypatch it deterministically regardless of integration's progress.
"""

from __future__ import annotations

import importlib.util
import logging
import uuid

from app.config import get_settings

logger = logging.getLogger(__name__)


def _impl():
    """Return integration's payments module, or None if not present yet."""
    try:
        if importlib.util.find_spec("app.services.payments") is None:
            return None
        from app.services import payments  # type: ignore

        return payments
    except ImportError:
        logger.exception("payments module present but failed to import")
        return None


def create_order(amount_rupees: int, receipt: str) -> dict:
    mod = _impl()
    if mod is not None:
        return mod.create_order(amount_rupees, receipt)
    # Fallback while phase 3 is pending — structurally valid payment object.
    settings = get_settings()
    return {
        "razorpay_order_id": f"order_stub_{uuid.uuid4().hex[:20]}",
        "razorpay_amount": int(amount_rupees) * 100,  # paise
        "razorpay_currency": "INR",
        "key_id": settings.razorpay_key_id or "rzp_test_stub_key",
    }


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    mod = _impl()
    if mod is not None:
        return bool(mod.verify_payment(order_id, payment_id, signature))
    # Cannot validate signatures without Razorpay credentials — integration fills this in.
    return False


def refund(payment_id: str, amount_rupees: int | None = None) -> dict:
    mod = _impl()
    if mod is not None:
        return mod.refund(payment_id, amount_rupees)
    logger.warning("payments.py unavailable — refund for %s not queued", payment_id)
    return {"status": "not_configured"}


def verify_webhook(body: bytes, signature: str) -> bool:
    mod = _impl()
    if mod is not None:
        return bool(mod.verify_webhook(body, signature))
    return False
