"""Razorpay payments service — implements the frozen interface in docs/CONTRACT.md.

Contract signatures (must not change):

    create_order(amount_rupees: int, receipt: str) -> dict
    verify_payment(order_id: str, payment_id: str, signature: str) -> bool
    refund(payment_id: str, amount_rupees: int | None = None) -> dict
    verify_webhook(body: bytes, signature: str) -> bool

Env: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET.
Optional: RAZORPAY_MOCK=1 (offline mock gateway — no HTTP; local/demo test
bypass: ``verify_payment`` accepts any non-empty order/payment/signature triple
per contract 2026-09-24 — webhook HMAC stays real), RAZORPAY_API_BASE_URL
(defaults to https://api.razorpay.com/v1). Never enable mock in production.

Amounts: rupees → paise ×100 for every gateway field. DB/JSON amounts stay in rupees
except ``razorpay_amount`` which is paise per contract.

Booking persistence helpers (find/confirm/refund-mark) live here because salon-integration
owns only payments.py + webhooks* + hold_expiry.py; they are used by the webhook endpoint
and by ``refund()``. Lookups are defensive (SQLAlchemy Core reflection) so they work with
whatever column aliases the booking model uses.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid
from functools import lru_cache
from typing import Any, Mapping, Optional

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import MetaData, Table, inspect, or_, select, update
from sqlalchemy.orm import Session

from app.services import hold_expiry  # noqa: F401  — imported for hold-expiry worker auto-start side effect

logger = logging.getLogger("app.payments")

# Column-name candidates on the bookings table (contract names first, aliases after).
_ORDER_ID_COLUMNS = ("razorpay_order_id", "order_id", "rzp_order_id")
_PAYMENT_ID_COLUMNS = ("razorpay_payment_id", "payment_id", "rzp_payment_id")
_BOOKING_PK_COLUMNS = ("id", "booking_id", "uuid")
_STATUS_COLUMN = "status"
_STATUS_PENDING = "pending_payment"
_STATUS_CONFIRMED = "confirmed"
_STATUS_CANCELLED = "cancelled"
_STATUS_REFUNDED = "refunded"


class PaymentsError(RuntimeError):
    """Razorpay gateway / configuration failure."""


class RazorpaySettings(BaseSettings):
    """Payment credentials from environment / .env (never hard-code secrets)."""

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_api_base_url: str = "https://api.razorpay.com/v1"
    razorpay_mock: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_razorpay_settings() -> RazorpaySettings:
    return RazorpaySettings()


# ---------------------------------------------------------------------------
# Contract interface
# ---------------------------------------------------------------------------


def create_order(amount_rupees: int, receipt: str) -> dict:
    """Create a Razorpay order for the advance amount.

    Returns the contract ``payment`` object keys (razorpay_order_id,
    razorpay_amount in paise, razorpay_currency, key_id) plus raw Razorpay-style
    aliases (id/amount/currency/receipt/status) for caller convenience.
    """
    try:
        amount_rupees = int(amount_rupees)
    except (TypeError, ValueError) as exc:
        raise ValueError("amount_rupees must be an integer number of rupees") from exc
    if amount_rupees <= 0:
        raise ValueError("amount_rupees must be positive")
    if not receipt or not str(receipt).strip():
        raise ValueError("receipt is required")

    # On-read hold sweep: releasing expired unpaid holds when new orders arrive.
    # Best-effort — booking creation must not fail because of the sweeper.
    try:
        hold_expiry.sweep_expired_holds()
    except Exception:  # noqa: BLE001 — deliberately best-effort
        logger.debug("hold-expiry sweep skipped during create_order", exc_info=True)

    amount_paise = amount_rupees * 100
    settings = get_razorpay_settings()

    if settings.razorpay_mock:
        order_id = f"order_mock_{_sanitize(receipt)}_{uuid.uuid4().hex[:10]}"
        status = "created"
    else:
        data = _razorpay_request(
            "POST",
            "/orders",
            {"amount": amount_paise, "currency": "INR", "receipt": str(receipt)},
        )
        order_id = data.get("id")
        if not order_id:
            raise PaymentsError("razorpay order response missing id")
        status = str(data.get("status") or "created")

    key_id = settings.razorpay_key_id or ("rzp_test_mock" if settings.razorpay_mock else "")
    return {
        # Contract payment-object keys (POST /bookings → "payment").
        "razorpay_order_id": order_id,
        "razorpay_amount": amount_paise,
        "razorpay_currency": "INR",
        "key_id": key_id,
        # Raw Razorpay-style aliases (callers may read order["id"] / order["amount"]).
        "id": order_id,
        "amount": amount_paise,
        "currency": "INR",
        "receipt": str(receipt),
        "status": status,
    }


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay checkout signature.

    Local/demo bypass (contract 2026-09-24): when ``RAZORPAY_MOCK=1``, returns
    ``True`` if ``order_id``, ``payment_id`` and ``signature`` are all
    non-empty strings after ``strip()`` — HMAC is skipped. Never enable mock
    in production (``RAZORPAY_MOCK=0`` + real keys).

    Otherwise: HMAC-SHA256 over ``order_id|payment_id`` with
    RAZORPAY_KEY_SECRET. Fails closed (False) when the secret or inputs are
    missing.
    """
    settings = get_razorpay_settings()
    if settings.razorpay_mock:
        return (
            _non_empty_str(order_id)
            and _non_empty_str(payment_id)
            and _non_empty_str(signature)
        )
    secret = settings.razorpay_key_secret
    if not secret or not order_id or not payment_id or not signature:
        return False
    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(signature))


def refund(payment_id: str, amount_rupees: int | None = None) -> dict:
    """Refund a payment (full amount when ``amount_rupees`` is None).

    Raises PaymentsError/ValueError on failure. On success, best-effort marks the
    booking ``cancelled → refunded`` (the ``refund.processed`` webhook is the
    durable backstop and is idempotent).
    """
    if not payment_id or not str(payment_id).strip():
        raise ValueError("payment_id is required")

    json_body: dict | None = None
    if amount_rupees is not None:
        try:
            amount_rupees = int(amount_rupees)
        except (TypeError, ValueError) as exc:
            raise ValueError("amount_rupees must be an integer number of rupees") from exc
        if amount_rupees <= 0:
            raise ValueError("amount_rupees must be positive")
        json_body = {"amount": amount_rupees * 100}

    settings = get_razorpay_settings()
    if settings.razorpay_mock:
        data: dict[str, Any] = {
            "id": f"rfnd_mock_{uuid.uuid4().hex[:10]}",
            "payment_id": payment_id,
            "status": "processed",
            "amount": (json_body or {}).get("amount"),
        }
    else:
        data = _razorpay_request("POST", f"/payments/{payment_id}/refund", json_body)

    if str(data.get("status") or "").lower() == "failed":
        raise PaymentsError(f"razorpay refund failed for {payment_id}: {data}")

    # Best-effort transition cancelled → refunded (own session; webhook backstops).
    try:
        from app.db import SessionLocal  # local import: keeps module import light

        db = SessionLocal()
        try:
            attempt_refund_mark(db, payment_id=str(payment_id))
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — refund must not fail if booking is unreachable
        logger.debug("refund mark skipped for %s", payment_id, exc_info=True)

    refund_id = data.get("id") or data.get("refund_id") or ""
    return {
        "id": refund_id,
        "razorpay_refund_id": refund_id,
        "payment_id": str(payment_id),
        "status": str(data.get("status") or "processed"),
        "amount": data.get("amount") if data.get("amount") is not None else (json_body or {}).get("amount"),
        "currency": data.get("currency", "INR"),
    }


def verify_webhook(body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature: HMAC-SHA256(raw body, RAZORPAY_WEBHOOK_SECRET)."""
    secret = get_razorpay_settings().razorpay_webhook_secret
    if not secret or not body or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(signature))


# ---------------------------------------------------------------------------
# Gateway HTTP (monkeypatch target for tests: ``payments._razorpay_request``)
# ---------------------------------------------------------------------------


def _razorpay_request(method: str, path: str, json_body: dict | None = None) -> dict:
    settings = get_razorpay_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise PaymentsError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not configured")
    url = f"{settings.razorpay_api_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = httpx.request(
            method,
            url,
            json=json_body,
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise PaymentsError(f"razorpay request failed: {exc}") from exc
    if response.status_code >= 400:
        raise PaymentsError(
            f"razorpay {method} {path} -> {response.status_code}: {response.text[:300]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise PaymentsError("razorpay returned non-JSON response") from exc


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value))[:40] or "receipt"


def _non_empty_str(value: object) -> bool:
    """True only for ``str`` with non-whitespace content (mock verify bypass)."""
    return isinstance(value, str) and bool(value.strip())


# ---------------------------------------------------------------------------
# Booking persistence helpers (Core reflection — tolerant of column aliases)
# ---------------------------------------------------------------------------


def _reflect_table(db: Session, name: str) -> Optional[Table]:
    bind = db.get_bind()
    try:
        if not inspect(bind).has_table(name):
            return None
        return Table(name, MetaData(), autoload_with=bind)
    except Exception:  # noqa: BLE001 — missing DB/table must not explode webhooks
        logger.debug("could not reflect table %s", name, exc_info=True)
        return None


def _pick_column(table: Table, candidates: tuple[str, ...]) -> Optional[str]:
    for name in candidates:
        if name in table.c:
            return name
    return None


def _pk_name(table: Table) -> str:
    pk_cols = list(table.primary_key.columns)
    if pk_cols:
        return pk_cols[0].name
    return _pick_column(table, _BOOKING_PK_COLUMNS) or "id"


def find_booking_by_order_id(db: Session, order_id: str | None) -> Optional[Mapping[str, Any]]:
    """Locate a booking row by its stored Razorpay order id (any known alias)."""
    if not order_id:
        return None
    table = _reflect_table(db, "bookings")
    if table is None:
        return None
    col = _pick_column(table, _ORDER_ID_COLUMNS)
    if col is None:
        return _find_booking_via_payments_table(db, order_id=str(order_id), payment_id=None)
    row = db.execute(select(table).where(table.c[col] == str(order_id))).mappings().first()
    return row


def find_booking_by_payment_id(db: Session, payment_id: str | None) -> Optional[Mapping[str, Any]]:
    """Locate a booking row by its stored Razorpay payment id (any known alias)."""
    if not payment_id:
        return None
    table = _reflect_table(db, "bookings")
    if table is None:
        return None
    col = _pick_column(table, _PAYMENT_ID_COLUMNS)
    if col is not None:
        row = db.execute(select(table).where(table.c[col] == str(payment_id))).mappings().first()
        if row is not None:
            return row
    return _find_booking_via_payments_table(db, order_id=None, payment_id=str(payment_id))


def _find_booking_via_payments_table(
    db: Session, *, order_id: str | None, payment_id: str | None
) -> Optional[Mapping[str, Any]]:
    """Fallback: a separate ``payments`` table mapping order/payment → booking_id."""
    payments_table = _reflect_table(db, "payments")
    if payments_table is None:
        return None
    order_col = _pick_column(payments_table, _ORDER_ID_COLUMNS)
    payment_col = _pick_column(payments_table, _PAYMENT_ID_COLUMNS)
    stmt = select(payments_table)
    matched = False
    if order_id and order_col is not None:
        stmt = stmt.where(payments_table.c[order_col] == order_id)
        matched = True
    elif payment_id and payment_col is not None:
        stmt = stmt.where(payments_table.c[payment_col] == payment_id)
        matched = True
    if not matched:
        return None
    pay_row = db.execute(stmt).mappings().first()
    if pay_row is None:
        return None
    for candidate in ("booking_id", "booking", "booking_uuid"):
        if candidate in pay_row:
            bookings = _reflect_table(db, "bookings")
            if bookings is None:
                return None
            pk = _pk_name(bookings)
            return (
                db.execute(select(bookings).where(bookings.c[pk] == pay_row[candidate]))
                .mappings()
                .first()
            )
    return None


def attempt_confirm_booking(
    db: Session,
    *,
    order_id: str | None,
    payment_id: str | None,
    amount_paise: int | None = None,
) -> str:
    """Idempotent ``pending_payment → confirmed`` transition (caller commits).

    Returns one of: ``confirmed``, ``already_processed``, ``hold_expired``,
    ``booking_not_found``, ``ignored``.
    The UPDATE is conditional on status + unexpired hold so concurrent webhooks
    cannot double-confirm.
    """
    from datetime import datetime, timezone

    booking = find_booking_by_order_id(db, order_id)
    if booking is None and payment_id:
        booking = find_booking_by_payment_id(db, payment_id)
    if booking is None:
        logger.info("webhook confirm: booking not found (order=%s)", order_id)
        return "booking_not_found"

    table = _reflect_table(db, "bookings")
    if table is None or _STATUS_COLUMN not in table.c:
        return "booking_not_found"
    pk = _pk_name(table)
    booking_id = booking[pk]
    status = str(booking[_STATUS_COLUMN] or "")

    if status == _STATUS_CONFIRMED:
        return "already_processed"
    if status != _STATUS_PENDING:
        logger.info("webhook confirm: booking %s in status %s — ignored", booking_id, status)
        return "ignored"

    values: dict[str, Any] = {_STATUS_COLUMN: _STATUS_CONFIRMED}
    payment_col = _pick_column(table, _PAYMENT_ID_COLUMNS)
    if payment_col is not None and payment_id:
        values[payment_col] = str(payment_id)
    paid_col = "online_amount_paid"
    if paid_col in table.c:
        if "advance_amount" in table.c and booking["advance_amount"] is not None:
            values[paid_col] = int(booking["advance_amount"])
        elif amount_paise is not None:
            values[paid_col] = int(amount_paise) // 100

    stmt = update(table).where(table.c[pk] == booking_id)
    stmt = stmt.where(table.c[_STATUS_COLUMN] == _STATUS_PENDING)
    if "expires_at" in table.c:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(or_(table.c["expires_at"].is_(None), table.c["expires_at"] > now))
    stmt = stmt.values(**values)

    result = db.execute(stmt)
    if result.rowcount:
        logger.info("webhook confirm: booking %s confirmed (payment=%s)", booking_id, payment_id)
        return "confirmed"

    # Conditional UPDATE lost the race — re-read to classify.
    refreshed = db.execute(select(table).where(table.c[pk] == booking_id)).mappings().first()
    refreshed_status = str(refreshed[_STATUS_COLUMN]) if refreshed else status
    if refreshed_status == _STATUS_CONFIRMED:
        return "already_processed"
    if refreshed_status == _STATUS_PENDING:
        return "hold_expired"
    return "ignored"


def attempt_refund_mark(
    db: Session, *, payment_id: str | None, order_id: str | None = None
) -> str:
    """Idempotent ``cancelled → refunded`` transition (caller commits).

    Returns one of: ``refunded``, ``already_processed``, ``booking_not_found``,
    ``ignored``.
    """
    booking = find_booking_by_payment_id(db, payment_id)
    if booking is None and order_id:
        booking = find_booking_by_order_id(db, order_id)
    if booking is None:
        logger.info("refund mark: booking not found (payment=%s)", payment_id)
        return "booking_not_found"

    table = _reflect_table(db, "bookings")
    if table is None or _STATUS_COLUMN not in table.c:
        return "booking_not_found"
    pk = _pk_name(table)
    status = str(booking[_STATUS_COLUMN] or "")

    if status == _STATUS_REFUNDED:
        return "already_processed"
    if status != _STATUS_CANCELLED:
        logger.info(
            "refund mark: booking %s in status %s (expected cancelled) — ignored",
            booking[pk],
            status,
        )
        return "ignored"

    stmt = (
        update(table)
        .where(table.c[pk] == booking[pk])
        .where(table.c[_STATUS_COLUMN] == _STATUS_CANCELLED)
        .values({_STATUS_COLUMN: _STATUS_REFUNDED})
    )
    result = db.execute(stmt)
    if result.rowcount:
        logger.info("refund mark: booking %s refunded (payment=%s)", booking[pk], payment_id)
        return "refunded"

    refreshed = db.execute(select(table).where(table.c[pk] == booking[pk])).mappings().first()
    if refreshed is not None and str(refreshed[_STATUS_COLUMN]) == _STATUS_REFUNDED:
        return "already_processed"
    return "ignored"
