"""Phase 4 — admin bookings list/filter, complete/no_show, dashboard."""

import uuid
from datetime import timedelta

from app.core.timeutil import utcnow
from app.db import SessionLocal
from app.models import Booking
from tests.conftest import (
    confirm_booking,
    create_booking,
    service_ids,
    future_day,
)


def _confirmed_booking(client, customer_headers, *, name="Haircut", barber_id=1, hour=10, addons=None):
    day = future_day()
    sid = service_ids(client)[name]
    created = create_booking(
        client,
        customer_headers,
        service_id=sid,
        barber_id=barber_id,
        day=day,
        hour=hour,
        addons=addons,
    )
    return day, confirm_booking(client, customer_headers, created)


def test_admin_bookings_list_filters(client, customer_headers, admin_headers):
    day = future_day()
    _, b1 = _confirmed_booking(client, customer_headers, hour=10, barber_id=1)
    _, b2 = _confirmed_booking(client, customer_headers, name="Beard trim", hour=12, barber_id=2)

    # unfiltered day list
    resp = client.get(
        "/admin/bookings", params={"date": day.isoformat()}, headers=admin_headers
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {i["id"] for i in items} == {b1["id"], b2["id"]}

    # barber filter
    resp = client.get(
        "/admin/bookings",
        params={"date": day.isoformat(), "barber_id": 2},
        headers=admin_headers,
    )
    assert [i["id"] for i in resp.json()["items"]] == [b2["id"]]

    # status filter
    resp = client.get(
        "/admin/bookings",
        params={"date": day.isoformat(), "status": "confirmed"},
        headers=admin_headers,
    )
    assert len(resp.json()["items"]) == 2

    resp = client.get(
        "/admin/bookings",
        params={"date": day.isoformat(), "status": "cancelled"},
        headers=admin_headers,
    )
    assert resp.json()["items"] == []

    # invalid status → 422
    resp = client.get(
        "/admin/bookings", params={"status": "bogus"}, headers=admin_headers
    )
    assert resp.status_code == 422

    # authz
    assert client.get("/admin/bookings", headers=customer_headers).status_code == 403
    assert client.get("/admin/bookings").status_code == 401


def test_complete_fixed_service_balance_math(client, customer_headers, admin_headers):
    _, booking = _confirmed_booking(client, customer_headers, hour=10)  # ₹100, advance 50
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete"},
    )
    assert resp.status_code == 200
    done = resp.json()["booking"]
    assert done["status"] == "completed"
    assert done["final_price_at_center"] == 100  # defaults to total for fixed
    assert done["balance_due"] == 100 - 50  # final - online_amount_paid


def test_complete_fixed_service_with_explicit_final(client, customer_headers, admin_headers):
    _, booking = _confirmed_booking(client, customer_headers, hour=10)
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete", "final_price_at_center": 150},
    )
    assert resp.status_code == 200
    assert resp.json()["booking"]["balance_due"] == 150 - 50


def test_complete_hair_color_requires_final_price(client, customer_headers, admin_headers):
    _, booking = _confirmed_booking(client, customer_headers, name="Hair color", hour=11)
    assert booking["advance_amount"] == 100
    assert booking["online_amount_paid"] == 100

    # missing final_price_at_center → 400
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "final_price_at_center_required"

    # with final → balance_due = final - online paid
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete", "final_price_at_center": 450},
    )
    assert resp.status_code == 200
    done = resp.json()["booking"]
    assert done["status"] == "completed"
    assert done["final_price_at_center"] == 450
    assert done["balance_due"] == 350  # 450 - 100

    # customer GET reflects the final + balance
    got = client.get(f"/bookings/{booking['id']}", headers=customer_headers)
    body = got.json()
    assert body["final_price_at_center"] == 450
    assert body["balance_due"] == 350


def test_no_show_action(client, customer_headers, admin_headers):
    _, booking = _confirmed_booking(client, customer_headers, hour=10)
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "no_show"},
    )
    assert resp.status_code == 200
    assert resp.json()["booking"]["status"] == "no_show"

    # can't complete afterwards
    resp = client.patch(
        f"/admin/bookings/{booking['id']}",
        headers=admin_headers,
        json={"action": "complete", "final_price_at_center": 200},
    )
    assert resp.status_code == 400


def test_admin_patch_authz_and_404(client, customer_headers, admin_headers):
    day = future_day()
    sid = service_ids(client)["Haircut"]
    created = create_booking(client, customer_headers, service_id=sid, day=day, hour=10)
    bid = created["booking"]["id"]

    assert (
        client.patch(
            f"/admin/bookings/{bid}",
            headers=customer_headers,
            json={"action": "no_show"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/admin/bookings/{bid}", json={"action": "no_show"}
        ).status_code
        == 401
    )
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.patch(
            f"/admin/bookings/{missing}",
            headers=admin_headers,
            json={"action": "no_show"},
        ).status_code
        == 404
    )
    # bad action → 422
    resp = client.patch(
        f"/admin/bookings/{bid}", headers=admin_headers, json={"action": "explode"}
    )
    assert resp.status_code == 422


def test_dashboard_aggregates(client, customer_headers, admin_headers):
    day = future_day()
    # A: haircut 10:00 barber 1 → confirmed → completed (default final 100, online 50)
    _, a = _confirmed_booking(client, customer_headers, hour=10, barber_id=1)
    # B: beard trim 12:00 barber 2 → stays confirmed (online 25)
    _, b = _confirmed_booking(
        client, customer_headers, name="Beard trim", hour=12, barber_id=2
    )
    # C: cancelled booking must not count as an active booking
    sid = service_ids(client)["Haircut"]
    c = create_booking(
        client, customer_headers, service_id=sid, hour=14, barber_id=3, day=day
    )
    cancel = client.post(
        f"/bookings/{c['booking']['id']}/cancel", headers=customer_headers
    )
    assert cancel.status_code == 200

    # complete A
    done = client.patch(
        f"/admin/bookings/{a['id']}",
        headers=admin_headers,
        json={"action": "complete"},
    )
    assert done.status_code == 200

    resp = client.get(
        "/admin/dashboard", params={"date": day.isoformat()}, headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == day.isoformat()
    assert body["bookings_count"] == 2  # A completed + B confirmed (cancelled excluded)
    assert body["confirmed_count"] == 1  # B
    assert body["revenue_online"] == 50 + 25  # A + B advances captured
    assert body["revenue_at_center"] == 50  # A balance_due (100 - 50)

    # authz
    assert client.get("/admin/dashboard", headers=customer_headers).status_code == 403
    assert client.get("/admin/dashboard").status_code == 401


def test_dashboard_defaults_to_today(client, admin_headers):
    resp = client.get("/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200
    from app.core.timeutil import kolkata_date

    assert resp.json()["date"] == kolkata_date(utcnow()).isoformat()
    assert resp.json()["bookings_count"] == 0
    assert resp.json()["revenue_online"] == 0
    assert resp.json()["revenue_at_center"] == 0
