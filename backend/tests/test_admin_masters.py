"""Phase 1 — admin CRUD authorization + services/barbers/schedule management."""


def test_admin_requires_token(client):
    assert client.get("/admin/services").status_code == 401
    assert client.post("/admin/services", json={}).status_code == 401


def test_admin_forbidden_for_customer(client, customer_headers):
    resp = client.get("/admin/services", headers=customer_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_authorized"


def test_admin_list_services_includes_inactive(client, admin_headers):
    resp = client.get("/admin/services", headers=admin_headers)
    assert resp.status_code == 200
    names = [i["name"] for i in resp.json()["items"]]
    assert "Head massage" in names  # inactive rows visible to admin
    assert "Haircut" in names


def test_admin_service_crud(client, admin_headers, customer_headers):
    create = client.post(
        "/admin/services",
        headers=admin_headers,
        json={
            "name": "Kids haircut",
            "description": "Under 10 years",
            "duration_minutes": 30,
            "price": 80,
        },
    )
    assert create.status_code == 201
    svc = create.json()
    assert svc["price"] == 80
    assert svc["price_type"] == "fixed"
    assert svc["is_active"] is True
    sid = svc["id"]

    # Not visible publicly until… it IS active — deactivate then check.
    patch = client.patch(
        f"/admin/services/{sid}",
        headers=admin_headers,
        json={"price": 90, "is_active": False},
    )
    assert patch.status_code == 200
    assert patch.json()["price"] == 90
    assert patch.json()["is_active"] is False

    public = [i["name"] for i in client.get("/services").json()["items"]]
    assert "Kids haircut" not in public

    delete = client.delete(f"/admin/services/{sid}", headers=admin_headers)
    assert delete.status_code == 204
    assert client.patch(
        f"/admin/services/{sid}", headers=admin_headers, json={"price": 1}
    ).status_code == 404

    # customers can't touch admin CRUD
    assert client.post(
        "/admin/services",
        headers=customer_headers,
        json={"name": "X", "duration_minutes": 15, "price": 10},
    ).status_code == 403


def test_admin_delete_service_in_use_409(client, admin_headers, customer_headers, db):
    from tests.conftest import create_booking, future_day, service_ids

    sid = service_ids(client)["Haircut"]
    create_booking(
        client, customer_headers, service_id=sid, day=future_day(), hour=10
    )
    resp = client.delete(f"/admin/services/{sid}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "in_use"


def test_admin_barber_crud(client, admin_headers):
    create = client.post(
        "/admin/barbers",
        headers=admin_headers,
        json={"name": "New Barber", "bio": "skin fades", "specialties": ["Fades"]},
    )
    assert create.status_code == 201
    barber = create.json()
    assert barber["specialties"] == ["Fades"]
    bid = barber["id"]

    patch = client.patch(
        f"/admin/barbers/{bid}", headers=admin_headers, json={"is_active": False}
    )
    assert patch.status_code == 200
    assert patch.json()["is_active"] is False

    # inactive barber hidden from public catalog
    public_ids = [b["id"] for b in client.get("/barbers").json()["items"]]
    assert bid not in public_ids

    assert client.delete(f"/admin/barbers/{bid}", headers=admin_headers).status_code == 204
    # gone: PATCH on missing id → 404 (no GET /admin/barbers/{id} in contract)
    assert (
        client.patch(
            f"/admin/barbers/{bid}", headers=admin_headers, json={"bio": "x"}
        ).status_code
        == 404
    )


def test_admin_schedule_put_get_roundtrip(client, admin_headers):
    # use barber 1
    payload = [
        {"weekday": w, "open_time": "10:00", "close_time": "21:00", "is_closed": False}
        for w in range(7)
    ]
    payload[6]["is_closed"] = True  # Sunday closed

    put = client.put("/admin/barbers/1/schedule", headers=admin_headers, json=payload)
    assert put.status_code == 200, put.text
    rows = put.json()
    assert len(rows) == 7
    assert rows[0]["open_time"] == "10:00"
    assert rows[6]["weekday"] == 6
    assert rows[6]["is_closed"] is True

    got = client.get("/admin/barbers/1/schedule", headers=admin_headers)
    assert got.status_code == 200
    assert got.json() == rows

    # invalid hours rejected
    bad = client.put(
        "/admin/barbers/1/schedule",
        headers=admin_headers,
        json=[{"weekday": 0, "open_time": "21:00", "close_time": "10:00", "is_closed": False}],
    )
    assert bad.status_code == 400

    # missing barber
    assert client.get("/admin/barbers/999/schedule", headers=admin_headers).status_code == 404


def test_admin_schedule_requires_admin(client, customer_headers):
    resp = client.get("/admin/barbers/1/schedule", headers=customer_headers)
    assert resp.status_code == 403
