"""Phase 8 — guest booking API (contract 2026-09-24).

Covers: optional auth on POST /bookings, 400 guest_identity_required,
find-or-create by phone (no clobber of password accounts), guest JWT session
for verify / get / cancel / list, overlap 409, and the guest user schema
(``is_guest`` + nullable ``email``).
"""

from __future__ import annotations

from sqlalchemy import select, text

from app.models import User
from tests.conftest import (  # noqa: F401 — fixtures resolved via module namespace
    ADMIN_PHONE,
    CUSTOMER1,
    create_booking,
    future_day,
    service_ids,
    slot_utc,
)

GUEST_NAME = "Walk-in Guest"
GUEST_PHONE = "9876543219"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def guest_body(
    client,
    *,
    day=None,
    hour: int = 10,
    minute: int = 0,
    barber_id: int = 1,
    addons: list[str] | None = None,
    guest_name: str | None = GUEST_NAME,
    guest_phone: str | None = GUEST_PHONE,
) -> dict:
    """Valid booking body; guest_* keys omitted when passed None."""
    day = day or future_day()
    body = {
        "service_id": service_ids(client)["Haircut"],
        "addons": addons or [],
        "barber_id": barber_id,
        "start_at": slot_utc(day, hour, minute).isoformat().replace("+00:00", "Z"),
        "notes": "",
    }
    if guest_name is not None:
        body["guest_name"] = guest_name
    if guest_phone is not None:
        body["guest_phone"] = guest_phone
    return body


def test_guest_create_without_token_returns_session(client, db):
    day = future_day()
    resp = client.post("/bookings", json=guest_body(client, day=day, hour=10))
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Session fields present ONLY on the guest-create path.
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    user = body["user"]
    assert user["role"] == "customer"
    assert user["email"] is None  # nullable-email scheme for pure guests
    assert user["name"] == GUEST_NAME
    assert user["phone"] == GUEST_PHONE  # stored normalized 10-digit

    booking = body["booking"]
    assert booking["status"] == "pending_payment"
    assert booking["guest_name"] == GUEST_NAME
    assert booking["guest_phone"] == GUEST_PHONE
    assert body["payment"]["razorpay_order_id"]
    assert body["payment"]["razorpay_amount"] == booking["advance_amount"] * 100

    db.expire_all()
    row = db.scalar(select(User).where(User.phone == GUEST_PHONE))
    assert row is not None
    assert row.is_guest is True
    assert row.email is None

    # The issued token is a normal JWT — /auth/me accepts it.
    me = client.get("/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["user"]["id"] == user["id"]


def test_guest_identity_required_400_when_missing_or_invalid(client):
    day = future_day()
    base = guest_body(client, day=day, hour=11, guest_name=None, guest_phone=None)
    cases: list[tuple[str, dict]] = [
        ("neither field", {}),
        ("name only", {"guest_name": "Only Name"}),
        ("phone only", {"guest_phone": GUEST_PHONE}),
        ("null phone", {"guest_name": "X", "guest_phone": None}),
        ("blank name", {"guest_name": "   ", "guest_phone": GUEST_PHONE}),
        ("short phone", {"guest_name": "X", "guest_phone": "12345"}),
        ("bare prefix", {"guest_name": "X", "guest_phone": "+91"}),
        ("bad leading digit form", {"guest_name": "X", "guest_phone": "05"}),
        ("non digits", {"guest_name": "X", "guest_phone": "abcdefghij"}),
        ("name over 80", {"guest_name": "N" * 81, "guest_phone": GUEST_PHONE}),
    ]
    for label, extra in cases:
        resp = client.post("/bookings", json={**base, **extra})
        assert resp.status_code == 400, f"{label}: {resp.text}"
        assert resp.json()["detail"] == "guest_identity_required", label


def test_guest_phone_formats_normalise_and_reuse_one_user(client):
    day = future_day()
    r1 = client.post(
        "/bookings",
        json=guest_body(
            client, day=day, hour=10, guest_name="Format Test",
            guest_phone="+919876543217",
        ),
    )
    assert r1.status_code == 201, r1.text
    uid = r1.json()["user"]["id"]
    assert r1.json()["user"]["phone"] == "9876543217"

    # Same number, bare 10-digit → same account; existing name preserved.
    r2 = client.post(
        "/bookings",
        json=guest_body(
            client, day=day, hour=12, guest_name="Different Name",
            guest_phone="9876543217",
        ),
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["user"]["id"] == uid
    assert r2.json()["user"]["name"] == "Format Test"

    # Same number with 0-prefix → same account again.
    r3 = client.post(
        "/bookings",
        json=guest_body(
            client, day=day, hour=14, guest_name="Another",
            guest_phone="09876543217",
        ),
    )
    assert r3.status_code == 201, r3.text
    assert r3.json()["user"]["id"] == uid


def test_guest_can_verify_payment_with_guest_token(client, fake_payments):
    day = future_day()
    created = client.post("/bookings", json=guest_body(client, day=day, hour=10))
    assert created.status_code == 201, created.text
    created = created.json()
    gh = bearer(created["access_token"])

    resp = client.post(
        f"/bookings/{created['booking']['id']}/verify-payment",
        headers=gh,
        json={
            "razorpay_order_id": created["payment"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_guest_1",
            "razorpay_signature": "sig_guest",
        },
    )
    assert resp.status_code == 200, resp.text
    booking = resp.json()["booking"]
    assert booking["status"] == "confirmed"
    assert booking["online_amount_paid"] == booking["advance_amount"] == 50
    assert fake_payments.created[-1][0] == 50  # haircut 50% advance


def test_guest_can_list_get_and_ownership_is_enforced(client):
    day = future_day()
    created = client.post("/bookings", json=guest_body(client, day=day, hour=10))
    assert created.status_code == 201, created.text
    created = created.json()
    gh = bearer(created["access_token"])
    bid = created["booking"]["id"]

    lst = client.get("/bookings", headers=gh)
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == bid
    assert items[0]["guest_name"] == GUEST_NAME

    got = client.get(f"/bookings/{bid}", headers=gh)
    assert got.status_code == 200
    assert got.json()["id"] == bid

    # Anonymous → 401; another guest → 404 (no existence leak).
    assert client.get("/bookings").status_code == 401
    assert client.get(f"/bookings/{bid}").status_code == 401
    other = client.post(
        "/bookings",
        json=guest_body(
            client, day=day, hour=13, guest_name="Other Guest",
            guest_phone="9876543216",
        ),
    )
    assert other.status_code == 201, other.text
    oh = bearer(other.json()["access_token"])
    assert client.get(f"/bookings/{bid}", headers=oh).status_code == 404
    assert client.post(f"/bookings/{bid}/cancel", headers=oh).status_code == 404


def test_guest_can_cancel_with_guest_token(client, fake_payments):
    day = future_day()
    created = client.post("/bookings", json=guest_body(client, day=day, hour=10))
    assert created.status_code == 201, created.text
    created = created.json()
    gh = bearer(created["access_token"])
    bid = created["booking"]["id"]

    resp = client.post(f"/bookings/{bid}/cancel", headers=gh)
    assert resp.status_code == 200, resp.text
    assert resp.json()["booking"]["status"] == "cancelled"
    assert resp.json()["booking"]["cancellation_reason"] == "customer"
    assert fake_payments.refunded == []  # unpaid hold — nothing captured

    # Cancelled hold cannot be cancelled again.
    again = client.post(f"/bookings/{bid}/cancel", headers=gh)
    assert again.status_code == 400
    assert again.json()["detail"] == "invalid_status"


def test_registered_path_still_works_and_ignores_guest_fields(
    client, customer_headers, customer, db
):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    resp = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    # Registered create: no session keys in the response.
    assert "access_token" not in resp
    assert "token_type" not in resp
    assert "user" not in resp
    # Booking still carries the owner's identity fields.
    assert resp["booking"]["guest_name"] == "Test Customer"
    assert resp["booking"]["guest_phone"] == "+919876543210"

    # Guest fields alongside a valid Bearer are ignored (contract: prefer ignore).
    spoof = guest_body(
        client, day=day, hour=12, barber_id=2,
        guest_name="Spoof Name", guest_phone="9800000001",
    )
    r = client.post("/bookings", headers=customer_headers, json=spoof)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "access_token" not in body
    # Linked to the registered customer — no spoofed account was created.
    assert body["booking"]["guest_name"] == "Test Customer"
    db.expire_all()
    assert db.scalar(select(User).where(User.phone == "9800000001")) is None
    assert (
        db.get(User, customer["user"]["id"]).phone == CUSTOMER1["phone"]
    )


def test_guest_overlap_still_409(client):
    day = future_day()
    first = client.post(
        "/bookings",
        json=guest_body(client, day=day, hour=10, guest_name="A",
                         guest_phone="9876543215"),
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/bookings",
        json=guest_body(client, day=day, hour=10, guest_name="B",
                         guest_phone="9876543214"),
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "slot_unavailable"


def test_guest_links_existing_password_account_without_clobbering(
    client, customer, db
):
    # `customer` registered CUSTOMER1 (phone +919876543210, password login).
    day = future_day()
    resp = client.post(
        "/bookings",
        json=guest_body(client, day=day, hour=10, guest_name="Impostor",
                         guest_phone="09876543210"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["id"] == customer["user"]["id"]
    assert body["user"]["name"] == "Test Customer"  # profile untouched
    assert body["user"]["email"] == CUSTOMER1["email"]

    db.expire_all()
    row = db.get(User, customer["user"]["id"])
    assert row.is_guest is False  # flag not flipped on existing accounts
    assert row.role == "customer"

    # Password account still works after the guest link.
    login = client.post(
        "/auth/login",
        json={"phone": CUSTOMER1["phone"], "password": CUSTOMER1["password"]},
    )
    assert login.status_code == 200


def test_guest_create_rejects_admin_phone_never_mints_token(client, db):
    """Contract follow-up: guest find-or-create is role=customer only."""
    day = future_day()
    resp = client.post(
        "/bookings",
        json=guest_body(client, day=day, hour=10, guest_name="Sneaky Admin",
                         guest_phone=ADMIN_PHONE),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "guest_identity_required"
    # No session, no booking — 400 detail only.
    body = resp.json()
    assert "access_token" not in body
    assert "booking" not in body

    # Admin account untouched (still logs in with its password).
    db.expire_all()
    admin = db.scalar(select(User).where(User.phone == ADMIN_PHONE))
    assert admin is not None and admin.role == "admin" and admin.is_guest is False

    # Same rejection for other non-customer roles.
    db.add(
        User(name="Staff", phone="9700000001", email="staff@salon.local",
             password_hash="x", role="admin", is_guest=False)
    )
    db.commit()
    resp2 = client.post(
        "/bookings",
        json=guest_body(client, day=day, hour=12, guest_name="Also Sneaky",
                         guest_phone="9700000001"),
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "guest_identity_required"


def test_users_schema_ships_is_guest_and_nullable_email(db):
    rows = db.execute(text("PRAGMA table_info(users)")).fetchall()
    cols = {row[1]: row for row in rows}
    assert "is_guest" in cols
    assert cols["email"][3] == 0  # notnull == 0 → nullable email

    # UNIQUE still permits multiple NULL emails (pure guests).
    db.add_all(
        [
            User(name="G1", phone="9000000001", email=None,
                 password_hash="x", role="customer", is_guest=True),
            User(name="G2", phone="9000000002", email=None,
                 password_hash="x", role="customer", is_guest=True),
        ]
    )
    db.commit()
