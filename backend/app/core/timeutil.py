"""UTC / Asia-Kolkata helpers.

Rules (AGENTS.md):
- All datetimes are stored and returned in UTC.
- Calendar-day math (availability `date`, dashboard `date`) uses Asia/Kolkata (UTC+05:30).
- Slot grid is 15 minutes.
"""

from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
SLOT_STEP_MINUTES = 15
SLOT_STEP = timedelta(minutes=SLOT_STEP_MINUTES)


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC (naive values are assumed UTC — SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_kolkata(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(IST)


def kolkata_date(dt: datetime) -> date:
    """Asia/Kolkata calendar day of a UTC instant."""
    return ensure_utc(dt).astimezone(IST).date()


def kolkata_day_bounds(d: date) -> tuple[datetime, datetime]:
    """UTC half-open interval [start, end) of an Asia/Kolkata calendar day."""
    start = datetime(d.year, d.month, d.day, tzinfo=IST)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def ist_local_to_utc(d: date, t: time) -> datetime:
    """Wall-clock `t` on IST calendar day `d` → UTC instant."""
    local = datetime(
        d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond, tzinfo=IST
    )
    return local.astimezone(UTC)


def iso_z(dt: datetime | None) -> str | None:
    """RFC3339 UTC string (…Z)."""
    if dt is None:
        return None
    s = ensure_utc(dt).isoformat()
    if s.endswith("+00:00"):
        s = s[: -len("+00:00")] + "Z"
    return s
