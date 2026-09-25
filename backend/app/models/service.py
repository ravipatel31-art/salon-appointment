"""Service catalog + global add-ons (seeded from AGENTS.md)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("price_type in ('fixed', 'variable_advance')", name="price_type"),
        CheckConstraint("price >= 0", name="price_nonneg"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int]
    price: Mapped[int]  # rupees; hair color is the ₹100 flat online advance
    price_type: Mapped[str] = mapped_column(String(24), default="fixed")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ServiceAddon(Base):
    """Global add-ons applicable to any service (id = slug, e.g. "wash")."""

    __tablename__ = "service_addons"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_nonneg"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[int]
    duration_minutes: Mapped[int]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
