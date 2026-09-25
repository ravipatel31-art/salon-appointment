"""User model — customers self-register; guests find-or-create by phone;
one admin from the seed script."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('customer', 'admin')", name="role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    # Nullable: pure guests (POST /bookings guest checkout) have no email —
    # UNIQUE still permits multiple NULLs on PostgreSQL and SQLite.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # True only when the row was first created via guest checkout (phone + name).
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
