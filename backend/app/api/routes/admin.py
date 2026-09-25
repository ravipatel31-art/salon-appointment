"""Admin endpoints (role=admin): masters CRUD, schedules, bookings, dashboard."""

import uuid as uuid_lib
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.bookings import booking_payload
from app.api.routes.catalog import barber_out, service_out
from app.core.deps import require_admin
from app.core.timeutil import kolkata_day_bounds, utcnow
from app.db import get_db
from app.models import (
    Barber,
    BarberSchedule,
    Booking,
    Service,
    ServiceAddon,
)
from app.schemas.booking import AdminBookingPatch
from app.schemas.catalog import BarberIn, BarberPatch, ScheduleRow, ServiceIn, ServicePatch

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

BOOKING_STATUS_VALUES = (
    "pending_payment",
    "confirmed",
    "completed",
    "cancelled",
    "refunded",
    "no_show",
)


# ---------------------------------------------------------------- services ---

@router.get("/services")
def admin_list_services(db: Session = Depends(get_db)) -> dict:
    services = db.scalars(select(Service).order_by(Service.id)).all()
    addons = db.scalars(
        select(ServiceAddon).where(ServiceAddon.is_active.is_(True)).order_by(ServiceAddon.id)
    ).all()
    return {"items": [service_out(s, addons) for s in services]}


@router.post("/services", status_code=201)
def admin_create_service(body: ServiceIn, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Service).where(Service.name == body.name)):
        raise HTTPException(status_code=409, detail="service_exists")
    service = Service(**body.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service_out(service, [])


@router.patch("/services/{service_id}")
def admin_patch_service(
    service_id: int, body: ServicePatch, db: Session = Depends(get_db)
) -> dict:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != service.name:
        if db.scalar(select(Service).where(Service.name == updates["name"])):
            raise HTTPException(status_code=409, detail="service_exists")
    for key, value in updates.items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return service_out(service, [])


@router.delete("/services/{service_id}", status_code=204)
def admin_delete_service(service_id: int, db: Session = Depends(get_db)) -> Response:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    db.delete(service)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="in_use")
    return Response(status_code=204)


# ----------------------------------------------------------------- barbers ---

@router.get("/barbers")
def admin_list_barbers(db: Session = Depends(get_db)) -> dict:
    barbers = db.scalars(select(Barber).order_by(Barber.id)).all()
    return {"items": [barber_out(b) for b in barbers]}


@router.post("/barbers", status_code=201)
def admin_create_barber(body: BarberIn, db: Session = Depends(get_db)) -> dict:
    barber = Barber(**body.model_dump())
    db.add(barber)
    db.commit()
    db.refresh(barber)
    return barber_out(barber)


@router.patch("/barbers/{barber_id}")
def admin_patch_barber(
    barber_id: int, body: BarberPatch, db: Session = Depends(get_db)
) -> dict:
    barber = db.get(Barber, barber_id)
    if barber is None:
        raise HTTPException(status_code=404, detail="barber_not_found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(barber, key, value)
    db.commit()
    db.refresh(barber)
    return barber_out(barber)


@router.delete("/barbers/{barber_id}", status_code=204)
def admin_delete_barber(barber_id: int, db: Session = Depends(get_db)) -> Response:
    barber = db.get(Barber, barber_id)
    if barber is None:
        raise HTTPException(status_code=404, detail="barber_not_found")
    db.delete(barber)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="in_use")
    return Response(status_code=204)


# --------------------------------------------------------------- schedules ---

def _schedule_out(row: BarberSchedule) -> dict:
    return {
        "weekday": row.weekday,
        "open_time": row.open_time.strftime("%H:%M"),
        "close_time": row.close_time.strftime("%H:%M"),
        "is_closed": row.is_closed,
    }


@router.get("/barbers/{barber_id}/schedule")
def admin_get_schedule(barber_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Barber, barber_id) is None:
        raise HTTPException(status_code=404, detail="barber_not_found")
    rows = db.scalars(
        select(BarberSchedule)
        .where(BarberSchedule.barber_id == barber_id)
        .order_by(BarberSchedule.weekday)
    ).all()
    return [_schedule_out(r) for r in rows]


@router.put("/barbers/{barber_id}/schedule")
def admin_put_schedule(
    barber_id: int, body: list[ScheduleRow], db: Session = Depends(get_db)
) -> list[dict]:
    if db.get(Barber, barber_id) is None:
        raise HTTPException(status_code=404, detail="barber_not_found")
    weekdays = [row.weekday for row in body]
    if len(set(weekdays)) != len(weekdays):
        raise HTTPException(status_code=400, detail="duplicate_weekday")
    for row in body:
        if row.open_time >= row.close_time:
            raise HTTPException(status_code=400, detail="invalid_hours")

    db.execute(
        delete(BarberSchedule).where(BarberSchedule.barber_id == barber_id)
    )
    for row in body:
        db.add(
            BarberSchedule(
                barber_id=barber_id,
                weekday=row.weekday,
                open_time=time.fromisoformat(row.open_time),
                close_time=time.fromisoformat(row.close_time),
                is_closed=row.is_closed,
            )
        )
    db.commit()
    return admin_get_schedule(barber_id, db)


# ---------------------------------------------------------------- bookings ---

@router.get("/bookings")
def admin_list_bookings(
    date: date | None = Query(default=None, description="Asia/Kolkata day filter"),
    barber_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Booking)
    if date is not None:
        day_start, day_end = kolkata_day_bounds(date)
        stmt = stmt.where(Booking.start_at >= day_start, Booking.start_at < day_end)
    if barber_id is not None:
        stmt = stmt.where(Booking.barber_id == barber_id)
    if status is not None:
        if status not in BOOKING_STATUS_VALUES:
            raise HTTPException(status_code=422, detail="invalid_status")
        stmt = stmt.where(Booking.status == status)
    rows = db.scalars(stmt.order_by(Booking.start_at.asc())).all()
    return {"items": [booking_payload(b, include_names=True) for b in rows]}


@router.patch("/bookings/{booking_id}")
def admin_patch_booking(
    booking_id: uuid_lib.UUID,
    body: AdminBookingPatch,
    db: Session = Depends(get_db),
) -> dict:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking_not_found")
    if booking.status not in ("pending_payment", "confirmed"):
        raise HTTPException(status_code=400, detail="invalid_status")

    if body.action == "complete":
        service = db.get(Service, booking.service_id)
        if service is not None and service.price_type == "variable_advance":
            if body.final_price_at_center is None:
                raise HTTPException(
                    status_code=400, detail="final_price_at_center_required"
                )
            final = body.final_price_at_center
        else:
            final = body.final_price_at_center or booking.total_amount
        booking.final_price_at_center = final
        booking.balance_due = final - booking.online_amount_paid
        booking.status = "completed"
    else:  # no_show
        booking.status = "no_show"

    db.commit()
    db.refresh(booking)
    return {"booking": booking_payload(booking, include_names=True)}


# --------------------------------------------------------------- dashboard ---

@router.get("/dashboard")
def admin_dashboard(
    date: date | None = Query(default=None, description="Asia/Kolkata day, default today"),
    db: Session = Depends(get_db),
) -> dict:
    from app.core.timeutil import kolkata_date

    day = date if date is not None else kolkata_date(utcnow())
    day_start, day_end = kolkata_day_bounds(day)

    day_bookings = list(
        db.scalars(
            select(Booking).where(
                Booking.start_at >= day_start, Booking.start_at < day_end
            )
        ).all()
    )
    active = [b for b in day_bookings if b.status not in ("cancelled", "refunded")]
    confirmed_count = sum(1 for b in day_bookings if b.status == "confirmed")
    revenue_online = sum(
        b.online_amount_paid
        for b in day_bookings
        if b.status in ("confirmed", "completed", "no_show")
    )
    revenue_at_center = sum(
        b.balance_due or 0 for b in day_bookings if b.status == "completed"
    )
    return {
        "date": day.isoformat(),
        "bookings_count": len(active),
        "confirmed_count": confirmed_count,
        "revenue_online": revenue_online,
        "revenue_at_center": revenue_at_center,
    }
