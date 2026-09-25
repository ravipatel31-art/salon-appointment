"""Phase 1 — seed catalog matches AGENTS.md exactly + public catalog endpoints."""

from datetime import time

from sqlalchemy import select

from app.models import Barber, BarberSchedule, Service, ServiceAddon
from app.seed import BARBER_NAMES, BARBER_PHOTO_URLS, run_seed, seed_catalog

# AGENTS.md catalog — single source of truth.
EXPECTED_SERVICES = {
    "Haircut": {"price": 100, "duration_minutes": 60, "price_type": "fixed", "active": True},
    "Shaving": {"price": 70, "duration_minutes": 30, "price_type": "fixed", "active": True},
    "Beard trim": {"price": 50, "duration_minutes": 15, "price_type": "fixed", "active": True},
    "Head massage": {"price": 0, "duration_minutes": 30, "price_type": "fixed", "active": False},
    "Massage + Haircut": {"price": 200, "duration_minutes": 90, "price_type": "fixed", "active": True},
    "Shaving + Massage": {"price": 130, "duration_minutes": 60, "price_type": "fixed", "active": True},
    "Full combo": {"price": 250, "duration_minutes": 120, "price_type": "fixed", "active": True},
    "Hair color": {"price": 100, "duration_minutes": 90, "price_type": "variable_advance", "active": True},
    "Haircut + Shaving": {"price": 180, "duration_minutes": 90, "price_type": "fixed", "active": True},
    "Haircut + Beard trim": {"price": 130, "duration_minutes": 75, "price_type": "fixed", "active": True},
}


def test_seed_catalog_matches_agents_md(db):
    services = {s.name: s for s in db.scalars(select(Service)).all()}
    assert set(services) == set(EXPECTED_SERVICES)
    for name, spec in EXPECTED_SERVICES.items():
        svc = services[name]
        assert svc.price == spec["price"], name
        assert svc.duration_minutes == spec["duration_minutes"], name
        assert svc.price_type == spec["price_type"], name
        assert svc.is_active is spec["active"], name

    wash = db.get(ServiceAddon, "wash")
    assert wash is not None
    assert (wash.price, wash.duration_minutes) == (30, 15)
    assert wash.is_active is True

    barbers = db.scalars(select(Barber)).all()
    assert len(barbers) == 5
    for barber in barbers:
        rows = db.scalars(
            select(BarberSchedule).where(BarberSchedule.barber_id == barber.id)
        ).all()
        assert len(rows) == 7  # full week
        by_day = {r.weekday: r for r in rows}
        assert by_day[0].open_time == time(9, 0)  # Monday
        assert by_day[6].close_time == time(18, 0)  # Sunday


def test_seed_is_idempotent(db, admin_headers):
    before = {
        "services": len(db.scalars(select(Service)).all()),
        "barbers": len(db.scalars(select(Barber)).all()),
    }
    counts = run_seed(db, phone="+911234567890", password="admin-secret-1")
    assert counts["services"] == 0
    assert counts["addons"] == 0
    assert counts["barbers"] == 0
    assert counts["schedules"] == 0
    assert counts["admin"] == "+911234567890"
    db.expire_all()
    assert len(db.scalars(select(Service)).all()) == before["services"]
    assert len(db.scalars(select(Barber)).all()) == before["barbers"]


def test_seed_adds_missing_services_to_already_seeded_db(db):
    """A running volume seeded with only the original 8 services picks up the
    two new combo rows on re-run — without duplicating anything."""
    new_names = ("Haircut + Shaving", "Haircut + Beard trim")
    for name in new_names:
        row = db.scalar(select(Service).where(Service.name == name))
        assert row is not None, name
        db.delete(row)
    db.commit()

    counts = seed_catalog(db)
    assert counts["services"] == len(new_names)
    assert counts["addons"] == 0
    assert counts["barbers"] == 0
    assert counts["schedules"] == 0

    db.expire_all()
    services = db.scalars(select(Service)).all()
    assert {s.name for s in services} == set(EXPECTED_SERVICES)
    ids = [s.id for s in services]
    assert len(ids) == len(set(ids))  # no id collisions after re-insert
    for s in services:
        if s.name in new_names:
            assert s.price == EXPECTED_SERVICES[s.name]["price"]
            assert s.duration_minutes == EXPECTED_SERVICES[s.name]["duration_minutes"]

    # second pass is a pure no-op
    counts = seed_catalog(db)
    assert counts["services"] == 0


def test_seed_barber_photo_urls(db):
    """Phase 11 — 5 stable HTTPS demo portraits; fill null/empty only."""
    assert set(BARBER_PHOTO_URLS) == set(BARBER_NAMES)
    assert len(set(BARBER_PHOTO_URLS.values())) == 5  # unique per barber
    for url in BARBER_PHOTO_URLS.values():
        assert url.startswith("https://")

    barbers = db.scalars(select(Barber)).all()
    assert len(barbers) == 5
    for barber in barbers:
        assert barber.photo_url == BARBER_PHOTO_URLS[barber.name]

    # null / empty → back-filled on re-run; non-empty (admin) → preserved.
    null_one = next(b for b in barbers if b.name == "Rahul Sharma")
    empty_one = next(b for b in barbers if b.name == "Amit Patel")
    custom = next(b for b in barbers if b.name == "Vikram Singh")
    null_one.photo_url = None
    empty_one.photo_url = "   "
    custom.photo_url = "https://cdn.example.com/custom.jpg"
    db.commit()

    counts = seed_catalog(db)
    assert counts["photo_urls"] == 2
    db.expire_all()
    by_name = {b.name: b for b in db.scalars(select(Barber)).all()}
    assert by_name["Rahul Sharma"].photo_url == BARBER_PHOTO_URLS["Rahul Sharma"]
    assert by_name["Amit Patel"].photo_url == BARBER_PHOTO_URLS["Amit Patel"]
    assert by_name["Vikram Singh"].photo_url == "https://cdn.example.com/custom.jpg"

    # Second pass is a no-op.
    assert seed_catalog(db)["photo_urls"] == 0


def test_public_services_shape(client):
    resp = client.get("/services")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [i["name"] for i in items]
    # Head massage is a combo component — not publicly bookable.
    assert "Head massage" not in names
    assert set(EXPECTED_SERVICES) - {"Head massage"} <= set(names)

    haircut = next(i for i in items if i["name"] == "Haircut")
    assert haircut["price"] == 100
    assert haircut["duration_minutes"] == 60
    assert haircut["price_type"] == "fixed"
    assert haircut["is_active"] is True
    assert {"id": "wash", "name": "Wash", "price": 30, "duration_minutes": 15} in haircut["addons"]

    color = next(i for i in items if i["name"] == "Hair color")
    assert color["price"] == 100
    assert color["price_type"] == "variable_advance"


def test_public_barbers_shape(client):
    resp = client.get("/barbers")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 5
    for item in items:
        assert set(item) == {"id", "name", "photo_url", "bio", "specialties", "is_active"}
        assert item["is_active"] is True

    first = items[0]
    single = client.get(f"/barbers/{first['id']}")
    assert single.status_code == 200
    assert single.json()["name"] == first["name"]

    missing = client.get("/barbers/9999")
    assert missing.status_code == 404
