"""Phase 1 — auth flow (register / login / me)."""

from tests.conftest import CUSTOMER1


def test_register_returns_token_and_user(client):
    resp = client.post("/auth/register", json=CUSTOMER1)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    user = body["user"]
    assert user["role"] == "customer"
    assert user["email"] == CUSTOMER1["email"]
    assert user["phone"] == CUSTOMER1["phone"]


def test_register_duplicate_email_409(client, customer):
    dup = dict(CUSTOMER1, phone="+911112223334")
    resp = client.post("/auth/register", json=dup)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "email_already_registered"


def test_register_duplicate_phone_409(client, customer):
    dup = dict(CUSTOMER1, email="other@example.com")
    resp = client.post("/auth/register", json=dup)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "phone_already_registered"


def test_login_with_email_and_phone(client, customer):
    resp = client.post("/auth/login", json={"email": CUSTOMER1["email"], "password": CUSTOMER1["password"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    resp = client.post("/auth/login", json={"phone": CUSTOMER1["phone"], "password": CUSTOMER1["password"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password_401(client, customer):
    resp = client.post("/auth/login", json={"email": CUSTOMER1["email"], "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_credentials"


def test_login_requires_identifier(client):
    resp = client.post("/auth/login", json={"password": "whatever"})
    assert resp.status_code == 422


def test_me_with_token(client, customer_headers):
    resp = client.get("/auth/me", headers=customer_headers)
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["email"] == CUSTOMER1["email"]
    assert user["role"] == "customer"
    for key in ("id", "name", "phone", "email", "role"):
        assert key in user


def test_me_without_token_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token_401(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
