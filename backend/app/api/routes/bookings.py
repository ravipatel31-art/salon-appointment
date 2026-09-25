"""Customer bookings: create/hold, verify payment, list/get, cancel (CONTRACT §Bookings).

Auth on create is optional (guest checkout, contract 2026-09-24):
- Valid Bearer token → registered session (guest_name/guest_phone ignored).
- No Authorization header → guest_name + guest_phone required; server
  find-or-creates the customer by phone and returns a normal JWT session
  (access_token / token_type / user) for verify / cancel / list.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import token_response
from app.api.routes.catalog import get_active_barber, get_active_service
from app.config import get_settings
from app.core.deps import get_current_user, get_optional_user
from app.core.phone import normalize_india_mobile
from app.core.security import hash_password
from app.core.timeutil import ensure_utc, iso_z, kolkata_date, utcnow
from app.db import get_db
from app.models import Booking, User
from app.schemas.auth import VerifyPaymentIn
from app.schemas.booking import BookingCreate
from app.services import payment_interface
from app.services.availability import has_overlap, is_open_slot
from app.services.pricing import compute_amounts, duration_minutes, resolve_addons

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bookings"])


def booking_payload(booking: Booking, include_names: bool = False) -> dict:
    owner = booking.user
    payload = {
        "id": str(booking.id),
        "booking_ref": booking.booking_ref,
        "status": booking.status,
        "service_id": booking.service_id,
        "barber_id": booking.barber_id,
        "addons": booking.addons or [],
        "start_at": iso_z(booking.start_at),
        "end_at": iso_z(booking.end_at),
        "duration_minutes": booking.duration_minutes,
        "total_amount": booking.total_amount,
        "advance_amount": booking.advance_amount,
        "balance_amount": booking.balance_amount,
        "online_amount_paid": booking.online_amount_paid,
        "expires_at": iso_z(booking.expires_at),
        # Optional in contract — always present here; null until cancelled.
        "cancellation_reason": booking.cancellation_reason,
        # Optional in contract — booking identity (checkout name/phone for
        # guests; the registered customer's name/phone otherwise).
        "guest_name": owner.name if owner else None,
        "guest_phone": owner.phone if owner else None,
    }
    if include_names:
        payload["service_name"] = booking.service.name if booking.service else None
        payload["barber_name"] = booking.barber.name if booking.barber else None
        payload["final_price_at_center"] = booking.final_price_at_center
        payload["balance_due"] = booking.balance_due
    return payload


def _new_booking_ref(db: Session, start_at: datetime) -> str:
    """SL-<IST appointment yyyymmdd>-<seq:04d> e.g. SL-20260924-0042."""
    day = kolkata_date(start_at)
    prefix = f"SL-{day.strftime('%Y%m%d')}-"
    count = db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.booking_ref.startswith(prefix))
    ) or 0
    return f"{prefix}{count + 1:04d}"


def _normalize_payment(raw: dict, advance_rupees: int) -> dict:
    order_id = raw.get("razorpay_order_id") or raw.get("id") or ""
    amount = raw.get("razorpay_amount")
    if amount is None:
        amount = advance_rupees * 100
    return {
        "razorpay_order_id": order_id,
        "razorpay_amount": int(amount),
        "razorpay_currency": raw.get("razorpay_currency") or "INR",
        "key_id": raw.get("key_id") or get_settings().razorpay_key_id,
    }


def get_booking_for_user(db: Session, booking_id: uuid.UUID, user: User) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or (booking.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="booking_not_found")
    return booking


def _find_user_by_phone(db: Session, phone10: str) -> User | None:
    """Find an existing account by India mobile, tolerating stored formats."""
    variants = [phone10, f"+91{phone10}", f"0{phone10}", f"91{phone10}"]
    rows = db.scalars(select(User).where(User.phone.in_(variants))).all()
    for row in rows:
        if normalize_india_mobile(row.phone) == phone10:
            return row
    # Fallback for odd stored forms (e.g. "+910…" / extra prefix digits).
    rows = db.scalars(select(User).where(User.phone.like(f"%{phone10}"))).all()
    for row in rows:
        if normalize_india_mobile(row.phone) == phone10:
            return row
    return None


def resolve_guest_user(db: Session, body: BookingCreate) -> User:
    """Unauthenticated POST /bookings: validate identity, find-or-create by phone.

    Guest find-or-create is **role=customer only** (CONTRACT §Bookings,
    2026-09-24): a match on an admin / any role != customer is rejected with
    400 guest_identity_required — a bearer is never minted for non-customer
    roles from guest create.
    - Existing customer → linked as-is; profile/password and is_guest are
      never overwritten.
    - New phone → User(name, phone, role=customer, is_guest=true, email=null,
      password_hash=random unusable), phone stored as bare 10 digits.
    Raises 400 guest_identity_required when identity is missing/invalid or
    the phone belongs to a non-customer account.
    """
    name = (body.guest_name or "").strip()
    phone = normalize_india_mobile(body.guest_phone)
    if not name or len(name) > 80 or phone is None:
        raise HTTPException(status_code=400, detail="guest_identity_required")
    existing = _find_user_by_phone(db, phone)
    if existing is not None:
        if existing.role != "customer":
            # Admin/other roles must log in — no guest-session JWT for them.
            raise HTTPException(status_code=400, detail="guest_identity_required")
        return existing
    user = User(
        name=name,
        phone=phone,
        email=None,
        # Random plaintext nobody knows → unusable for password login.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="customer",
        is_guest=True,
    )
    db.add(user)
    db.flush()
    return user


@router.post("/bookings", status_code=201)
def create_booking(
    body: BookingCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    guest_session = user is None
    if guest_session:
        # Identity check first — 400 guest_identity_required wins over
        # slot/service errors so the Flutter checkout can prompt for details.
        user = resolve_guest_user(db, body)
    # guest_name / guest_phone are ignored when a valid Bearer is present.

    service = get_active_service(db, body.service_id)
    barber = get_active_barber(db, body.barber_id)
    addon_rows = resolve_addons(db, body.addons)
    addon_ids = [a.id for a in addon_rows]

    start_at = ensure_utc(body.start_at)
    duration = duration_minutes(service, addon_rows)
    end_at = start_at + timedelta(minutes=duration)
    now = utcnow()

    # Transactional slot check: schedule + grid + future + half-open overlap.
    if not is_open_slot(db, barber.id, start_at, duration, now):
        raise HTTPException(status_code=409, detail="slot_unavailable")

    total, advance, balance = compute_amounts(service, addon_rows)
    settings = get_settings()
    booking = Booking(
        booking_ref=_new_booking_ref(db, start_at),
        user_id=user.id,
        service_id=service.id,
        barber_id=barber.id,
        addons=addon_ids,
        start_at=start_at,
        end_at=end_at,
        duration_minutes=duration,
        total_amount=total,
        advance_amount=advance,
        balance_amount=balance,
        online_amount_paid=0,
        status="pending_payment",
        expires_at=now + timedelta(minutes=settings.booking_hold_minutes),
        notes=body.notes or "",
    )
    db.add(booking)
    db.flush()

    try:
        raw = payment_interface.create_order(advance, booking.booking_ref)
    except Exception as exc:  # pragma: no cover - depends on integration
        db.rollback()
        logger.exception("create_order failed")
        raise HTTPException(status_code=502, detail="payment_order_failed") from exc

    payment = _normalize_payment(raw, advance)
    if not payment["razorpay_order_id"]:
        db.rollback()
        raise HTTPException(status_code=502, detail="payment_order_failed")
    booking.razorpay_order_id = payment["razorpay_order_id"]
    db.commit()
    db.refresh(booking)
    payload = {"booking": booking_payload(booking), "payment": payment}
    if guest_session:
        # Guest create → issue the normal JWT session for verify/cancel/list
        # (omitted when the client already sent a valid Bearer token).
        payload.update(token_response(user))
    return payload


@router.post("/bookings/{booking_id}/verify-payment")
def verify_payment(
    booking_id: uuid.UUID,
    body: VerifyPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    booking = get_booking_for_user(db, booking_id, user)
    now = utcnow()

    if booking.status != "pending_payment":
        raise HTTPException(status_code=400, detail="invalid_status")
    if booking.expires_at is None or ensure_utc(booking.expires_at) <= now:
        raise HTTPException(status_code=400, detail="hold_expired")
    if body.razorpay_order_id != booking.razorpay_order_id:
        raise HTTPException(status_code=400, detail="order_mismatch")
    if not payment_interface.verify_payment(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="verification_failed")

    # Razorpay verify re-checks overlap before confirming (AGENTS.md).
    if has_overlap(
        db,
        booking.barber_id,
        ensure_utc(booking.start_at),
        ensure_utc(booking.end_at),
        now,
        exclude_id=booking.id,
    ):
        raise HTTPException(status_code=409, detail="slot_unavailable")

    booking.razorpay_payment_id = body.razorpay_payment_id
    booking.status = "confirmed"
    booking.online_amount_paid = booking.advance_amount
    db.commit()
    db.refresh(booking)
    return {"booking": booking_payload(booking, include_names=True)}


@router.get("/bookings")
def list_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(Booking)
        .where(Booking.user_id == user.id)
        .order_by(Booking.start_at.desc())
    ).all()
    return {"items": [booking_payload(b, include_names=True) for b in rows]}


@router.get("/bookings/{booking_id}")
def get_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    booking = get_booking_for_user(db, booking_id, user)
    return booking_payload(booking, include_names=True)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    booking = get_booking_for_user(db, booking_id, user)
    if booking.status not in ("pending_payment", "confirmed"):
        raise HTTPException(status_code=400, detail="invalid_status")

    now = utcnow()
    window = timedelta(hours=get_settings().cancel_refund_window_hours)
    if ensure_utc(booking.start_at) - now < window:
        raise HTTPException(status_code=403, detail="too_late_to_cancel")

    booking.status = "cancelled"
    booking.cancellation_reason = "customer"
    db.commit()
    db.refresh(booking)

    # Enqueue refund of the online advance; integration's job flips status to refunded.
    if booking.online_amount_paid > 0 and booking.razorpay_payment_id:
        try:
            payment_interface.refund(
                booking.razorpay_payment_id, booking.online_amount_paid
            )
        except Exception:  # pragma: no cover - depends on integration
            logger.exception("refund enqueue failed for %s", booking.booking_ref)

    return {"booking": booking_payload(booking, include_names=True)}
