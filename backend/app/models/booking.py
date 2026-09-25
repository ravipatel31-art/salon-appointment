"""Booking rows — amounts in rupees, datetimes UTC."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


BOOKING_STATUSES = (
    "pending_payment",
    "confirmed",
    "completed",
    "cancelled",
    "refunded",
    "no_show",
)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending_payment','confirmed','completed','cancelled','refunded','no_show')",
            name="status",
        ),
        CheckConstraint("advance_amount >= 0", name="advance_nonneg"),
        CheckConstraint(
            "cancellation_reason is null "
            "or cancellation_reason in ('hold_expired','customer')",
            name="cancellation_reason",
        ),
        Index("ix_bookings_barber_window", "barber_id", "start_at", "end_at"),
        Index("ix_bookings_user_start", "user_id", "start_at"),
        Index("ix_bookings_status_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_ref: Mapped[str] = mapped_column(String(24), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id"), index=True)
    addons: Mapped[list] = mapped_column(JSON, default=list)  # list of add-on ids e.g. ["wash"]

    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    duration_minutes: Mapped[int]

    total_amount: Mapped[int]  # rupees
    advance_amount: Mapped[int]  # rupees due online now
    balance_amount: Mapped[int]  # rupees total - advance (known at booking time)
    online_amount_paid: Mapped[int] = mapped_column(default=0)  # rupees captured online

    final_price_at_center: Mapped[int | None] = mapped_column(nullable=True)
    balance_due: Mapped[int | None] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="pending_payment")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)  # unpaid hold TTL
    # Optional cancel cause (CONTRACT §Bookings): 'hold_expired' | 'customer' | NULL.
    cancellation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    razorpay_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    user = relationship("User", lazy="joined")
    service = relationship("Service", lazy="joined")
    barber = relationship("Barber", lazy="joined")
