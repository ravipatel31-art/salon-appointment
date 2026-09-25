"""Barbers (data rows, no login) + weekly working schedules."""

from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Barber(Base):
    __tablename__ = "barbers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    specialties: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    schedules: Mapped[list["BarberSchedule"]] = relationship(
        back_populates="barber", cascade="all, delete-orphan"
    )


class BarberSchedule(Base):
    """Weekly hours. weekday: Monday=0 … Sunday=6 (Python date.weekday()). Times are Asia/Kolkata wall-clock."""

    __tablename__ = "barber_schedules"
    __table_args__ = (
        UniqueConstraint("barber_id", "weekday", name="uq_barber_schedules_barber_id"),
        CheckConstraint("weekday between 0 and 6", name="weekday_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    barber_id: Mapped[int] = mapped_column(
        ForeignKey("barbers.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int]
    open_time: Mapped[time]
    close_time: Mapped[time]
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    barber: Mapped[Barber] = relationship(back_populates="schedules")
