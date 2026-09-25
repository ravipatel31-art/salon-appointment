"""Shared test fixtures.

- DATABASE_URL is forced to a temp SQLite file *before* any app import so the
  app engine/session factory bind to it (runtime default remains PostgreSQL).
- Each test gets a fresh schema + AGENTS.md catalog + one admin user.
- ``payment_interface`` functions are monkeypatched with fakes so tests never
  depend on salon-integration's payments.py progress.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, time, timedelta

_TMPDIR = tempfile.mkdtemp(prefix="salon_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.core.timeutil import IST, UTC, ist_local_to_utc  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.seed import seed_catalog  # noqa: E402
from app.services import payment_interface  # noqa: E402

ADMIN_PHONE = "+911234567890"
ADMIN_EMAIL = "admin@salon.local"
ADMIN_PASSWORD = "admin-secret-1"

CUSTOMER1 = {
    "name": "Test Customer",
    "phone": "+919876543210",
    "email": "customer1@example.com",
    "password": "secret-123",
}
CUSTOMER2 = {
    "name": "Second Customer",
    "phone": "+919876543211",
    "email": "customer2@example.com",
    "password": "secret-123",
}

_admin_hash_cache: str | None = None


def _admin_hash() -> str:
    global _admin_hash_cache
    if _admin_hash_cache is None:
        _admin_hash_cache = hash_password(ADMIN_PASSWORD)
    return _admin_hash_cache


def future_day(offset_days: int = 14) -> date:
    """A deterministic future date on Mon–Sat (avoids Sunday's different hours)."""
    d = (datetime.now(IST) + timedelta(days=offset_days)).date()
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


def slot_utc(d: date, hour: int, minute: int = 0) -> datetime:
    """IST wall-clock (hour, minute) on day d → UTC instant."""
    return ist_local_to_utc(d, time(hour, minute))


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_catalog(db)
        db.add(
            User(
                name="Salon Admin",
                phone=ADMIN_PHONE,
                email=ADMIN_EMAIL,
                password_hash=_admin_hash(),
                role="admin",
            )
        )
        db.commit()
    finally:
        db.close()
    yield


class FakePayments:
    """Stand-in for services/payments.py (integration-owned)."""

    def __init__(self) -> None:
        self.created: list[tuple[int, str]] = []
        self.refunded: list[tuple[str, int | None]] = []
        self.verify_result = True

    def create_order(self, amount_rupees: int, receipt: str) -> dict:
        self.created.append((amount_rupees, receipt))
        return {
            "razorpay_order_id": f"order_test_{receipt}",
            "razorpay_amount": int(amount_rupees) * 100,
            "razorpay_currency": "INR",
            "key_id": "rzp_test_key",
        }

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        return self.verify_result

    def refund(self, payment_id: str, amount_rupees: int | None = None) -> dict:
        self.refunded.append((payment_id, amount_rupees))
        return {"status": "processed"}


@pytest.fixture(autouse=True)
def fake_payments(monkeypatch) -> FakePayments:
    fake = FakePayments()
    monkeypatch.setattr(payment_interface, "create_order", fake.create_order)
    monkeypatch.setattr(payment_interface, "verify_payment", fake.verify_payment)
    monkeypatch.setattr(payment_interface, "refund", fake.refund)
    return fake


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register(client: TestClient, data: dict) -> dict:
    resp = client.post("/auth/register", json=data)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def customer(client):
    return register(client, CUSTOMER1)


@pytest.fixture()
def customer2(client):
    return register(client, CUSTOMER2)


@pytest.fixture()
def customer_headers(customer) -> dict:
    return {"Authorization": f"Bearer {customer['access_token']}"}


@pytest.fixture()
def customer2_headers(customer2) -> dict:
    return {"Authorization": f"Bearer {customer2['access_token']}"}


@pytest.fixture()
def admin_headers(client) -> dict:
    resp = client.post(
        "/auth/login", json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def service_ids(client: TestClient) -> dict[str, int]:
    """Map service name → id from the seeded catalog."""
    resp = client.get("/services")
    assert resp.status_code == 200
    return {item["name"]: item["id"] for item in resp.json()["items"]}


def create_booking(
    client: TestClient,
    headers: dict,
    *,
    service_id: int,
    barber_id: int = 1,
    day: date | None = None,
    hour: int = 10,
    minute: int = 0,
    addons: list[str] | None = None,
    expect: int = 201,
) -> dict:
    day = day or future_day()
    resp = client.post(
        "/bookings",
        headers=headers,
        json={
            "service_id": service_id,
            "addons": addons or [],
            "barber_id": barber_id,
            "start_at": slot_utc(day, hour, minute).isoformat().replace("+00:00", "Z"),
            "notes": "",
        },
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


def confirm_booking(
    client: TestClient,
    headers: dict,
    booking: dict,
) -> dict:
    """Verify payment on a pending hold → confirmed."""
    resp = client.post(
        f"/bookings/{booking['booking']['id']}/verify-payment",
        headers=headers,
        json={
            "razorpay_order_id": booking["payment"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "sig_test",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["booking"]
