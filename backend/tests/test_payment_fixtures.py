"""Shared fixtures/helpers for payment, webhook and hold-expiry tests.

Owned by salon-integration (globs: ``backend/tests/test_payment*``,
``backend/tests/test_e2e*``). Contains no tests itself — other test modules
import the fixtures by name (pytest resolves fixtures from the test module
namespace).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.webhooks import router as webhooks_router
from app.db import get_db

# Test secrets (never real) — also used to compute valid HMAC signatures.
KEY_ID = "rzp_test_key"
KEY_SECRET = "test_key_secret"
WEBHOOK_SECRET = "test_webhook_secret"

UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def sign_webhook(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def sign_payment(order_id: str, payment_id: str, secret: str = KEY_SECRET) -> str:
    payload = f"{order_id}|{payment_id}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def payment_captured_event(
    *, order_id: str, payment_id: str, amount_paise: int, event: str = "payment.captured"
) -> bytes:
    payload = {
        "event": event,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "captured" if event == "payment.captured" else event.split(".")[-1],
                }
            }
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def refund_processed_event(
    *, payment_id: str, order_id: str, amount_paise: int, refund_id: str = "rfnd_test_1"
) -> bytes:
    payload = {
        "event": "refund.processed",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                }
            },
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": payment_id,
                    "amount": amount_paise,
                    "status": "processed",
                }
            },
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def post_webhook(
    client: TestClient, body: bytes, signature: str | None = None, secret: str = WEBHOOK_SECRET
):
    headers = {"Content-Type": "application/json"}
    headers["X-Razorpay-Signature"] = sign_webhook(body, secret) if signature is None else signature
    return client.post("/webhooks/razorpay", content=body, headers=headers)


class BookingStore:
    """Tiny bookings-table double (same column names production code expects)."""

    def __init__(self, engine: Any, session_factory: Callable[[], Any], table: Table) -> None:
        self.engine = engine
        self.Session = session_factory
        self.table = table

    def session(self):
        return self.Session()

    def add(self, **fields: Any) -> str:
        defaults: dict[str, Any] = {
            "id": "bk_0001",
            "booking_ref": "SL-20260924-0001",
            "status": "pending_payment",
            "start_at": now_utc() + timedelta(hours=3),
            "end_at": now_utc() + timedelta(hours=4),
            "expires_at": now_utc() + timedelta(minutes=12),
            "advance_amount": 65,
            "online_amount_paid": 0,
            "cancellation_reason": None,
            "razorpay_order_id": None,
            "razorpay_payment_id": None,
        }
        defaults.update(fields)
        db = self.session()
        try:
            db.execute(self.table.insert().values(**defaults))
            db.commit()
        finally:
            db.close()
        return str(defaults["id"])

    def get(self, booking_id: str) -> dict[str, Any] | None:
        db = self.session()
        try:
            row = (
                db.execute(
                    self.table.select().where(self.table.c["id"] == booking_id)
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None
        finally:
            db.close()

    def set(self, booking_id: str, **values: Any) -> None:
        db = self.session()
        try:
            db.execute(
                self.table.update()
                .where(self.table.c["id"] == booking_id)
                .values(**values)
            )
            db.commit()
        finally:
            db.close()


def _build_bookings_table(metadata: MetaData) -> Table:
    return Table(
        "bookings",
        metadata,
        Column("id", String, primary_key=True),
        Column("booking_ref", String),
        Column("status", String, nullable=False),
        Column("start_at", DateTime(timezone=True)),
        Column("end_at", DateTime(timezone=True)),
        Column("expires_at", DateTime(timezone=True)),
        Column("advance_amount", Integer),
        Column("online_amount_paid", Integer),
        Column("cancellation_reason", String),
        Column("razorpay_order_id", String),
        Column("razorpay_payment_id", String),
    )


@pytest.fixture
def razorpay_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Deterministic Razorpay test credentials (cleared settings cache around test)."""
    from app.services import payments

    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("RAZORPAY_MOCK", "0")
    payments.get_razorpay_settings.cache_clear()
    yield
    payments.get_razorpay_settings.cache_clear()


@pytest.fixture
def razorpay_mock_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Same credentials but offline mock gateway (no HTTP for create/refund).

    Also arms the contract 2026-09-24 verify bypass: any non-empty
    order/payment/signature triple verifies (HMAC skipped).
    """
    from app.services import payments

    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("RAZORPAY_MOCK", "1")
    payments.get_razorpay_settings.cache_clear()
    yield
    payments.get_razorpay_settings.cache_clear()


@pytest.fixture
def real_payments(fake_payments, monkeypatch: pytest.MonkeyPatch):
    """Phase 6 e2e: re-wire ``payment_interface`` to the *real* payments module.

    conftest's autouse ``fake_payments`` patches ``payment_interface`` first;
    this fixture depends on it explicitly so the real implementations win for
    the test. Gateway runs offline (``RAZORPAY_MOCK=1``) — per contract
    2026-09-24 ``verify_payment`` accepts any non-empty triple (no HMAC) while
    :func:`sign_payment` still produces real signatures for realism; webhook
    HMAC checks stay real. Env is set inline (not
    via ``razorpay_mock_env``) so this fixture resolves from any module that
    imports it without needing the other fixtures in its namespace.
    """
    from app.services import payment_interface, payments

    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("RAZORPAY_MOCK", "1")
    payments.get_razorpay_settings.cache_clear()
    monkeypatch.setattr(payment_interface, "create_order", payments.create_order)
    monkeypatch.setattr(payment_interface, "verify_payment", payments.verify_payment)
    monkeypatch.setattr(payment_interface, "refund", payments.refund)
    yield payments
    payments.get_razorpay_settings.cache_clear()


@pytest.fixture
def booking_store() -> Iterator[BookingStore]:
    """In-memory SQLite ``bookings`` table (StaticPool → one shared connection)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    table = _build_bookings_table(metadata)
    metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield BookingStore(engine, session_factory, table)
    engine.dispose()


@pytest.fixture
def webhook_app(booking_store: BookingStore) -> FastAPI:
    """FastAPI test app with only the webhook router + sqlite dependency override."""
    app = FastAPI()
    app.include_router(webhooks_router)

    def _override_get_db():
        session = booking_store.Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture
def webhook_client(webhook_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(webhook_app) as client:
        yield client
