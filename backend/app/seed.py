"""Seed script — AGENTS.md catalog + 5 barbers + weekly schedules + one admin.

Run after migrations:

    python -m app.seed          # uses ADMIN_PHONE / ADMIN_PASSWORD / ADMIN_EMAIL env

Idempotent: existing rows (matched by name / phone / email) are left as-is,
missing rows are inserted.
"""

from __future__ import annotations

import sys
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Barber, BarberSchedule, Service, ServiceAddon, User

# ---------------------------------------------------------------------------
# AGENTS.md catalog — do not invent other prices.
# ---------------------------------------------------------------------------

SERVICES: list[dict] = [
    {"name": "Haircut", "description": "", "duration_minutes": 60, "price": 100, "price_type": "fixed", "is_active": True},
    {"name": "Shaving", "description": "", "duration_minutes": 30, "price": 70, "price_type": "fixed", "is_active": True},
    {"name": "Beard trim", "description": "", "duration_minutes": 15, "price": 50, "price_type": "fixed", "is_active": True},
    # Combo component — no standalone online price, not bookable alone.
    {"name": "Head massage", "description": "Combo component", "duration_minutes": 30, "price": 0, "price_type": "fixed", "is_active": False},
    {"name": "Massage + Haircut", "description": "Head massage + haircut", "duration_minutes": 90, "price": 200, "price_type": "fixed", "is_active": True},
    {"name": "Shaving + Massage", "description": "Shaving + head massage", "duration_minutes": 60, "price": 130, "price_type": "fixed", "is_active": True},
    {"name": "Full combo", "description": "Haircut + beard trim + head massage + wash", "duration_minutes": 120, "price": 250, "price_type": "fixed", "is_active": True},
    # ₹100 flat online advance; actual price collected at the center.
    {"name": "Hair color", "description": "Actual price at center; ₹100 flat advance online", "duration_minutes": 90, "price": 100, "price_type": "variable_advance", "is_active": True},
    # Appended after the original 8 so existing rows keep ids 1–8 and these take
    # the next autoincrement ids (9, 10) on both fresh and already-seeded DBs.
    {"name": "Haircut + Shaving", "description": "Haircut + clean shave", "duration_minutes": 90, "price": 180, "price_type": "fixed", "is_active": True},
    {"name": "Haircut + Beard trim", "description": "Haircut + beard trim", "duration_minutes": 75, "price": 130, "price_type": "fixed", "is_active": True},
]

ADDONS: list[dict] = [
    {"id": "wash", "name": "Wash", "price": 30, "duration_minutes": 15, "is_active": True},
]

BARBER_NAMES: list[str] = [
    "Rahul Sharma",
    "Amit Patel",
    "Vikram Singh",
    "Suresh Kumar",
    "Imran Sheikh",
]

# Stable public demo portraits (CONTRACT.md → Imagery): absolute HTTPS, no
# auth, unique per barber via the `u=<slug>` seed on i.pravatar.cc. Applied on
# insert and back-filled when an existing row's photo_url is null/empty — a
# non-empty photo_url (e.g. admin PATCH) is never overwritten.
BARBER_PHOTO_URLS: dict[str, str] = {
    "Rahul Sharma": "https://i.pravatar.cc/300?u=salon-rahul-sharma",
    "Amit Patel": "https://i.pravatar.cc/300?u=salon-amit-patel",
    "Vikram Singh": "https://i.pravatar.cc/300?u=salon-vikram-singh",
    "Suresh Kumar": "https://i.pravatar.cc/300?u=salon-suresh-kumar",
    "Imran Sheikh": "https://i.pravatar.cc/300?u=salon-imran-sheikh",
}

# weekday: Monday=0 … Sunday=6. Times are Asia/Kolkata wall-clock.
DEFAULT_SCHEDULE: list[dict] = [
    {"weekday": 0, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Mon
    {"weekday": 1, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Tue
    {"weekday": 2, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Wed
    {"weekday": 3, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Thu
    {"weekday": 4, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Fri
    {"weekday": 5, "open_time": time(9, 0), "close_time": time(20, 0), "is_closed": False},   # Sat
    {"weekday": 6, "open_time": time(10, 0), "close_time": time(18, 0), "is_closed": False},  # Sun
]


def seed_catalog(db: Session) -> dict:
    """Insert missing services / add-ons / barbers / schedules. Idempotent."""
    counts = {"services": 0, "addons": 0, "barbers": 0, "schedules": 0, "photo_urls": 0}

    for spec in SERVICES:
        exists = db.scalar(select(Service).where(Service.name == spec["name"]))
        if exists is None:
            db.add(Service(**spec))
            counts["services"] += 1

    for spec in ADDONS:
        if db.get(ServiceAddon, spec["id"]) is None:
            db.add(ServiceAddon(**spec))
            counts["addons"] += 1

    for name in BARBER_NAMES:
        barber = db.scalar(select(Barber).where(Barber.name == name))
        if barber is None:
            barber = Barber(
                name=name,
                photo_url=BARBER_PHOTO_URLS.get(name),
                bio=f"Experienced stylist at the salon.",
                specialties=["Haircut", "Shave"],
                is_active=True,
            )
            db.add(barber)
            db.flush()
            counts["barbers"] += 1
            for row in DEFAULT_SCHEDULE:
                db.add(
                    BarberSchedule(
                        barber_id=barber.id,
                        weekday=row["weekday"],
                        open_time=row["open_time"],
                        close_time=row["close_time"],
                        is_closed=row["is_closed"],
                    )
                )
                counts["schedules"] += 1
        else:
            # Back-fill demo portrait only when missing; never overwrite a
            # non-empty photo_url (admin may have set a custom one).
            demo = BARBER_PHOTO_URLS.get(name)
            if demo and not (barber.photo_url or "").strip():
                barber.photo_url = demo
                counts["photo_urls"] += 1

    db.commit()
    return counts


def seed_admin(
    db: Session,
    phone: str | None = None,
    password: str | None = None,
    email: str | None = None,
    name: str | None = None,
) -> User | None:
    """Create the single admin user from env (ADMIN_PHONE / ADMIN_PASSWORD)."""
    settings = get_settings()
    phone = phone or settings.admin_phone
    password = password or settings.admin_password
    email = (email or settings.admin_email or "").strip().lower()
    name = name or settings.admin_name

    if not phone or not password:
        print("seed: ADMIN_PHONE / ADMIN_PASSWORD not set — skipping admin user")
        return None

    existing = db.scalar(select(User).where(User.phone == phone))
    if existing is not None:
        if existing.role != "admin":
            existing.role = "admin"
            db.commit()
        return existing

    if not email:
        email = f"{phone}@salon.local"
    if db.scalar(select(User).where(User.email == email)) is not None:
        email = f"admin+{phone}@salon.local"

    admin = User(
        name=name,
        phone=phone,
        email=email,
        password_hash=hash_password(password),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def run_seed(db: Session, **admin_kwargs) -> dict:
    counts = seed_catalog(db)
    admin = seed_admin(db, **admin_kwargs)
    counts["admin"] = admin.phone if admin else None
    return counts


def main() -> int:
    db = SessionLocal()
    try:
        counts = run_seed(db)
        print(f"seed complete: {counts}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
