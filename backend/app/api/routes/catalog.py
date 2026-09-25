"""Public catalog: services, barbers, availability (docs/CONTRACT.md §Catalog)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import iso_z, utcnow
from app.db import get_db
from app.models import Barber, Service, ServiceAddon
from app.services.availability import generate_slots
from app.services.pricing import duration_minutes, resolve_addons

router = APIRouter(tags=["catalog"])


def addon_out(a: ServiceAddon) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "price": a.price,
        "duration_minutes": a.duration_minutes,
    }


def service_out(s: Service, addons: list[ServiceAddon]) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "duration_minutes": s.duration_minutes,
        "price": s.price,
        "price_type": s.price_type,
        "is_active": s.is_active,
        "addons": [addon_out(a) for a in addons],
    }


def barber_out(b: Barber) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "photo_url": b.photo_url,
        "bio": b.bio,
        "specialties": b.specialties or [],
        "is_active": b.is_active,
    }


def get_active_service(db: Session, service_id: int) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    if not service.is_active:
        raise HTTPException(status_code=400, detail="service_inactive")
    return service


def get_active_barber(db: Session, barber_id: int) -> Barber:
    barber = db.get(Barber, barber_id)
    if barber is None or not barber.is_active:
        raise HTTPException(status_code=404, detail="barber_not_found")
    return barber


@router.get("/services")
def list_services(db: Session = Depends(get_db)) -> dict:
    services = db.scalars(
        select(Service).where(Service.is_active.is_(True)).order_by(Service.id)
    ).all()
    addons = db.scalars(
        select(ServiceAddon).where(ServiceAddon.is_active.is_(True)).order_by(ServiceAddon.id)
    ).all()
    return {"items": [service_out(s, addons) for s in services]}


@router.get("/barbers")
def list_barbers(db: Session = Depends(get_db)) -> dict:
    barbers = db.scalars(
        select(Barber).where(Barber.is_active.is_(True)).order_by(Barber.id)
    ).all()
    return {"items": [barber_out(b) for b in barbers]}


@router.get("/barbers/{barber_id}")
def get_barber(barber_id: int, db: Session = Depends(get_db)) -> dict:
    return barber_out(get_active_barber(db, barber_id))


@router.get("/barbers/{barber_id}/availability")
def availability(
    barber_id: int,
    date: date = Query(..., alias="date", description="Asia/Kolkata calendar day"),
    service_id: int = Query(...),
    addons: str = Query("", description="comma-separated add-on ids, e.g. wash"),
    db: Session = Depends(get_db),
) -> dict:
    """Available 15-min slots for that IST day, filtered by service+add-on duration."""
    barber = get_active_barber(db, barber_id)
    service = get_active_service(db, service_id)
    addon_ids = [x for x in addons.split(",") if x.strip()]
    addon_rows = resolve_addons(db, addon_ids)
    duration = duration_minutes(service, addon_rows)

    starts = generate_slots(db, barber, service, addon_rows, date, utcnow(), duration)
    return {
        "barber_id": barber.id,
        "date": date.isoformat(),
        "service_id": service.id,
        "duration_minutes": duration,
        "slots": [{"start_at": iso_z(t), "available": True} for t in starts],
    }
