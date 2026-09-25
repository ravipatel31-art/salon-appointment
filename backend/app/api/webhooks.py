"""Razorpay webhook endpoint — POST /webhooks/razorpay.

- Raw-body HMAC-SHA256 signature check (``X-Razorpay-Signature`` vs
  ``RAZORPAY_WEBHOOK_SECRET``) → 401 on failure.
- Idempotent by ``razorpay_payment_id``: the confirm/refund transitions are
  conditional UPDATEs (status-gated), so replays return 200
  ``already_processed`` without side effects.
- Confirms a booking only while it is still ``pending_payment`` **and** the
  hold is valid (not past ``expires_at``); performs an on-read hold-expiry
  sweep first.
- ``refund.processed`` events transition ``cancelled → refunded``.

Wiring: salon-backend includes ``app.api.webhooks.router`` in ``app.main``
(this file is owned by salon-integration; main.py is not).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import payments
from app.services.hold_expiry import sweep_expired_holds

logger = logging.getLogger("app.webhooks")

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # 1) Signature first — never touch the DB for unauthenticated traffic.
    if not payments.verify_webhook(body, signature):
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        event: dict[str, Any] = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_payload") from None
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    # 2) On-read hold sweep (releases expired unpaid slots).
    sweep_expired_holds(db)

    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    if not isinstance(payment_entity, dict):
        payment_entity = {}
    payment_id = payment_entity.get("id")
    order_id = payment_entity.get("order_id")
    amount_paise = payment_entity.get("amount")
    event_name = str(event.get("event") or "")

    if not payment_id and not order_id:
        db.commit()
        return JSONResponse(
            {"status": "ok", "event": event_name, "outcome": "ignored", "reason": "no_payment_entity"}
        )

    if event_name == "payment.failed":
        outcome = "ignored"
        reason = "payment_failed"
    elif event_name.startswith("refund."):
        outcome = (
            payments.attempt_refund_mark(
                db, payment_id=str(payment_id) if payment_id else None,
                order_id=str(order_id) if order_id else None,
            )
            if payment_id or order_id
            else "booking_not_found"
        )
        reason = None
    elif event_name.startswith("payment."):
        outcome = payments.attempt_confirm_booking(
            db,
            order_id=str(order_id) if order_id else None,
            payment_id=str(payment_id) if payment_id else None,
            amount_paise=int(amount_paise) if isinstance(amount_paise, (int, float)) else None,
        )
        reason = None
    else:
        outcome = "ignored"
        reason = "unknown_event"

    db.commit()

    body_out: dict[str, Any] = {"status": "ok", "event": event_name, "outcome": outcome}
    if payment_id:
        body_out["razorpay_payment_id"] = str(payment_id)
    if reason:
        body_out["reason"] = reason
    return JSONResponse(body_out)
