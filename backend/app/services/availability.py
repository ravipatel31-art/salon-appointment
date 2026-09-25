"""Availability engine (AGENTS.md booking rules).

- Slots: 15-minute grid inside the barber's weekly ``barber_schedules`` for the
  requested Asia/Kolkata calendar day.
- A slot fits only if ``start + duration <= close_time``.
- Blocking bookings: ``confirmed``, plus ``pending_payment`` holds that have not
  expired (expired holds free their slot again).
- Half-open overlap on ``(barber_id, [start_at, end_at))``.
- Past starts (``start <= now``) are never available.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import (
    SLOT_STEP,
    ensure_utc,
    ist_local_to_utc,
    kolkata_date,
)
from app.models import Barber, BarberSchedule, Booking, Service, ServiceAddon


def blocking_booking_conditions(
    barber_id: int, win_start: datetime, win_end: datetime, now: datetime
) -> list:
    return [
        Booking.barber_id == barber_id,
        Booking.start_at < win_end,
        Booking.end_at > win_start,
        or_(
            Booking.status == "confirmed",
            and_(
                Booking.status == "pending_payment",
                or_(Booking.expires_at.is_(None), Booking.expires_at > now),
            ),
        ),
    ]


def blocking_bookings(
    db: Session,
    barber_id: int,
    win_start: datetime,
    win_end: datetime,
    now: datetime,
    exclude_id=None,
) -> list[Booking]:
    conditions = blocking_booking_conditions(barber_id, win_start, win_end, now)
    if exclude_id is not None:
        conditions.append(Booking.id != exclude_id)
    return list(db.scalars(select(Booking).where(*conditions)))


def has_overlap(
    db: Session,
    barber_id: int,
    start: datetime,
    end: datetime,
    now: datetime,
    exclude_id=None,
) -> bool:
    """True when a blocking booking intersects [start, end) for this barber."""
    start = ensure_utc(start)
    end = ensure_utc(end)
    rows = blocking_bookings(db, barber_id, start, end, now, exclude_id=exclude_id)
    return len(rows) > 0


def get_schedule(db: Session, barber_id: int, day: date) -> BarberSchedule | None:
    """Weekly schedule row for that IST weekday (Monday=0 … Sunday=6)."""
    return db.scalar(
        select(BarberSchedule).where(
            BarberSchedule.barber_id == barber_id,
            BarberSchedule.weekday == day.weekday(),
        )
    )


def generate_slots(
    db: Session,
    barber: Barber,
    service: Service,
    addons: list[ServiceAddon],
    day: date,
    now: datetime,
    duration: int | None = None,
) -> list[datetime]:
    """Available start times (UTC) for an Asia/Kolkata calendar day, 15-min grid."""
    from app.services.pricing import duration_minutes as _dur

    duration = duration if duration is not None else _dur(service, addons)
    sched = get_schedule(db, barber.id, day)
    if sched is None or sched.is_closed:
        return []

    open_utc = ist_local_to_utc(day, sched.open_time)
    close_utc = ist_local_to_utc(day, sched.close_time)
    if close_utc <= open_utc:
        return []

    needed = timedelta(minutes=duration)
    occupied = [
        (ensure_utc(b.start_at), ensure_utc(b.end_at))
        for b in blocking_bookings(db, barber.id, open_utc, close_utc, now)
    ]

    slots: list[datetime] = []
    t = open_utc
    while t + needed <= close_utc:
        if t > now and not any(s < t + needed and e > t for s, e in occupied):
            slots.append(t)
        t += SLOT_STEP
    return slots


def is_open_slot(
    db: Session,
    barber_id: int,
    start: datetime,
    duration: int,
    now: datetime,
    exclude_id=None,
) -> bool:
    """True iff `start` would appear in generate_slots (grid, hours, future, free)."""
    start = ensure_utc(start)
    if start <= now:
        return False
    end = start + timedelta(minutes=duration)
    day = kolkata_date(start)
    sched = get_schedule(db, barber_id, day)
    if sched is None or sched.is_closed:
        return False
    open_utc = ist_local_to_utc(day, sched.open_time)
    close_utc = ist_local_to_utc(day, sched.close_time)
    if start < open_utc or end > close_utc:
        return False
    if (start - open_utc) % SLOT_STEP != timedelta(0):
        return False
    return not has_overlap(db, barber_id, start, end, now, exclude_id=exclude_id)
