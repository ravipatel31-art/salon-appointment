"""Phase 14 — SQL-injection hardening for the admin panel data path.

Proves that user-supplied text never reaches the database as code:

- Classic SQLi payloads in ``name`` / ``bio`` / ``description`` / ``photo_url``
  on ``POST`` + ``PATCH`` ``/admin/barbers`` and ``/admin/services``.
- Every probe responds **2xx or 422 only** (never 500).
- Row counts for ``users`` / ``bookings`` / ``barbers`` / ``services`` are
  unchanged after each probe (a ``DROP``/``DELETE`` would show up here).
- Free-text query params on admin/public reads never 500.
- Static audit of ``backend/app/**``: no f-string / ``format`` / ``%`` /
  concatenation-built SQL.
- Panel JS: no ``eval`` / ``new Function`` / ``document.write``; untrusted
  fields go through ``esc()``.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import func, select

from app.models import Barber, Booking, Service, User

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
PANEL_DIR = APP_DIR / "static" / "panel"

# Payloads from docs/CONTRACT.md phase 14 scope (admin CRUD text fields).
PAYLOADS = [
    "'; DROP TABLE users; --",
    "' OR '1'='1",
    "1; DELETE FROM bookings; --",
    "%27%20OR%201=1--",
]

TABLES: dict[str, type] = {
    "users": User,
    "barbers": Barber,
    "bookings": Booking,
    "services": Service,
}


# ---------------------------------------------------------------- helpers ---

def counts(db) -> dict[str, int]:
    """Fresh row counts (rollback first so an open snapshot can't hide rows)."""
    db.rollback()
    return {
        name: db.scalar(select(func.count()).select_from(model))
        for name, model in TABLES.items()
    }


def assert_no_5xx(resp, payload: str) -> None:
    assert resp.status_code < 500, (
        f"payload {payload!r} → HTTP {resp.status_code}: {resp.text[:400]}"
    )
    assert resp.status_code in (200, 201, 204, 400, 401, 403, 404, 409, 422), (
        f"payload {payload!r} → unexpected HTTP {resp.status_code}: {resp.text[:400]}"
    )


# ------------------------------------------------------- POST/PATCH probes ---

def test_barber_create_payloads(client, admin_headers, db):
    baseline = counts(db)
    created: list[int] = []

    for payload in PAYLOADS:
        resp = client.post(
            "/admin/barbers",
            headers=admin_headers,
            json={
                "name": payload,
                "bio": payload,
                "photo_url": payload,
                "specialties": [payload],
                "is_active": True,
            },
        )
        assert_no_5xx(resp, payload)
        assert resp.status_code in (201, 422), (payload, resp.status_code, resp.text)
        if resp.status_code == 201:
            created.append(resp.json()["id"])

        now = counts(db)
        # DROP/DELETE probes must leave the untouched tables exactly as they were.
        assert now["users"] == baseline["users"], f"users changed for {payload!r}"
        assert now["bookings"] == baseline["bookings"], f"bookings changed for {payload!r}"
        # barbers may only ever grow (one row per successful create).
        assert now["barbers"] >= baseline["barbers"], f"barbers shrank for {payload!r}"

    # Clean up probe rows → exact baseline restored (no orphan payloads).
    for barber_id in created:
        resp = client.delete(f"/admin/barbers/{barber_id}", headers=admin_headers)
        assert resp.status_code == 204, resp.text
    assert counts(db) == baseline


def test_barber_patch_payloads(client, admin_headers, db):
    baseline = counts(db)
    seeded = client.get("/admin/barbers", headers=admin_headers).json()["items"]
    target = seeded[0]["id"]

    for payload in PAYLOADS:
        resp = client.patch(
            f"/admin/barbers/{target}",
            headers=admin_headers,
            json={
                "name": payload,
                "bio": payload,
                "photo_url": payload,
                "specialties": [payload],
            },
        )
        assert_no_5xx(resp, payload)
        assert resp.status_code in (200, 422), (payload, resp.status_code, resp.text)
        # A PATCH must never add or remove rows.
        assert counts(db) == baseline, f"row counts changed for {payload!r}"

    # Seeded data still readable (table intact, row present).
    after = client.get("/admin/barbers", headers=admin_headers)
    assert after.status_code == 200
    assert any(b["id"] == target for b in after.json()["items"])


def test_service_create_payloads(client, admin_headers, db):
    baseline = counts(db)
    created: list[int] = []

    for payload in PAYLOADS:
        resp = client.post(
            "/admin/services",
            headers=admin_headers,
            json={
                "name": payload,
                "description": payload,
                "duration_minutes": 60,
                "price": 100,
                "price_type": "fixed",
                "is_active": True,
            },
        )
        assert_no_5xx(resp, payload)
        assert resp.status_code in (201, 422), (payload, resp.status_code, resp.text)
        if resp.status_code == 201:
            created.append(resp.json()["id"])

        now = counts(db)
        assert now["users"] == baseline["users"]
        assert now["bookings"] == baseline["bookings"]
        assert now["barbers"] == baseline["barbers"]
        assert now["services"] >= baseline["services"]

        # Delete immediately so the next payload can't hit a duplicate name.
        if resp.status_code == 201:
            del_resp = client.delete(
                f"/admin/services/{created[-1]}", headers=admin_headers
            )
            assert del_resp.status_code == 204, del_resp.text

    assert counts(db) == baseline


def test_service_patch_payloads(client, admin_headers, db):
    baseline = counts(db)
    seeded = client.get("/admin/services", headers=admin_headers).json()["items"]
    target = next(s["id"] for s in seeded if s["name"] == "Haircut")

    for payload in PAYLOADS:
        resp = client.patch(
            f"/admin/services/{target}",
            headers=admin_headers,
            json={"name": payload, "description": payload},
        )
        assert_no_5xx(resp, payload)
        assert resp.status_code in (200, 422), (payload, resp.status_code, resp.text)
        assert counts(db) == baseline, f"row counts changed for {payload!r}"

    # Restore a sane catalog row (this test's DB is per-test, but be tidy).
    client.patch(
        f"/admin/services/{target}",
        headers=admin_headers,
        json={"name": "Haircut", "description": ""},
    )


def test_probes_leave_admin_api_working(client, admin_headers, db):
    """Sweep every payload through both resources, then verify the API + tables."""
    baseline = counts(db)

    for payload in PAYLOADS:
        for path, body in (
            ("/admin/barbers", {"name": payload, "bio": payload,
                                "photo_url": payload, "specialties": [payload]}),
            ("/admin/services", {"name": payload, "description": payload,
                                 "duration_minutes": 30, "price": 50}),
        ):
            assert_no_5xx(client.post(path, headers=admin_headers, json=body), payload)
            # Repeated identical names are a legitimate 409 — never a 500.
            resp = client.post(path, headers=admin_headers, json=body)
            assert resp.status_code in (201, 409, 422), (
                payload, path, resp.status_code, resp.text
            )

    # Core tables never dropped/deleted.
    now = counts(db)
    assert now["users"] == baseline["users"]
    assert now["bookings"] == baseline["bookings"]
    assert now["barbers"] >= baseline["barbers"]
    assert now["services"] >= baseline["services"]

    # Seeded catalog + admin login still work after the probes.
    login = client.post(
        "/auth/login", json={"email": "admin@salon.local", "password": "admin-secret-1"}
    )
    assert login.status_code == 200, login.text

    barbers = client.get("/admin/barbers", headers=admin_headers)
    assert barbers.status_code == 200
    names = {b["name"] for b in barbers.json()["items"]}
    # AGENTS.md seed — none of the 5 seeded barbers were dropped/renamed away.
    for seeded_name in ("Rahul Sharma", "Amit Patel", "Vikram Singh",
                        "Suresh Kumar", "Imran Sheikh"):
        assert seeded_name in names, f"{seeded_name} missing from barbers"

    catalog = client.get("/services")
    assert catalog.status_code == 200
    names = {s["name"] for s in catalog.json()["items"]}
    assert "Haircut" in names and "Hair color" in names


def test_query_param_payloads_never_500(client, admin_headers, db):
    """Free-text / typed query params reject injection payloads without 500s."""
    baseline = counts(db)
    requests: list[tuple[str, dict]] = []

    for payload in PAYLOADS:
        requests += [
            ("/admin/bookings", {"status": payload}),
            ("/admin/bookings", {"date": payload}),
            ("/admin/bookings", {"barber_id": payload}),
            ("/admin/bookings", {"date": payload, "barber_id": payload,
                                 "status": payload}),
            ("/admin/dashboard", {"date": payload}),
            ("/admin/barbers", {"q": payload}),          # unknown params ignored
            ("/services", {"q": payload}),               # unknown params ignored
            ("/barbers/1/availability",
             {"date": payload, "service_id": 1}),
            ("/barbers/1/availability",
             {"date": "2030-01-07", "service_id": 1, "addons": payload}),
        ]

    for url, params in requests:
        resp = client.get(url, params=params, headers=admin_headers)
        assert resp.status_code < 500, (
            f"GET {url} {params} → {resp.status_code}: {resp.text[:300]}"
        )
        assert resp.status_code in (200, 400, 401, 403, 404, 422), (
            f"GET {url} {params} → unexpected {resp.status_code}: {resp.text[:300]}"
        )

    # The same payloads through a POST body (login) must stay safe too.
    for payload in PAYLOADS:
        post = client.post("/auth/login", json={"email": payload,
                                                "password": payload})
        assert post.status_code in (401, 422), (
            f"POST /auth/login {payload!r} → {post.status_code}: {post.text[:300]}"
        )

    # Status filter is whitelisted → validation error, never an SQL match.
    bad = client.get(
        "/admin/bookings", params={"status": "' OR '1'='1"}, headers=admin_headers
    )
    assert bad.status_code == 422
    assert counts(db) == baseline


# ------------------------------------------------ static audits (app + panel) ---

# String-built SQL patterns that must never appear in backend application code.
FORBIDDEN_SQL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:text|execute|exec_driver_sql)\s*\(\s*f\s*['\"]"),
     "f-string SQL"),
    (re.compile(r"\b(?:text|execute|exec_driver_sql)\s*\(\s*['\"][^'\"]*['\"]"
                r"\s*\.format\s*\("), "str.format() SQL"),
    (re.compile(r"\b(?:text|execute|exec_driver_sql)\s*\(\s*['\"][^'\"]*%[^'\"]*['\"]"
                r"\s*%"), "%-format SQL"),
    (re.compile(r"\b(?:text|execute|exec_driver_sql)\s*\(\s*[A-Za-z_][\w.]*\s*\+"),
     "string-concat SQL"),
    (re.compile(r"\b(?:text|execute|exec_driver_sql)\s*\(\s*f\s*'''"),
     "f-string triple-quoted SQL"),
]


def test_app_code_has_no_string_built_sql():
    """Audit: every SQL path in app/ uses ORM / bound parameters."""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for pattern, label in FORBIDDEN_SQL_PATTERNS:
            for match in pattern.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(BACKEND_DIR)}:{line}: {label}")
    assert not offenders, "string-built SQL found:\n" + "\n".join(offenders)


def test_panel_js_avoids_dynamic_code_and_escapes_html():
    """Panel: no eval/new Function/document.write; untrusted fields via esc()."""
    js = (PANEL_DIR / "app.js").read_text(encoding="utf-8")

    for banned in ("eval(", "new Function", "document.write",
                   'setTimeout("', 'setInterval("'):
        assert banned not in js, f"dynamic code execution found: {banned}"

    # esc() is defined and applied to every untrusted field the panel renders.
    assert "function esc(" in js
    for escaped in (
        "esc(b.name)",
        "esc(b.bio",
        "esc(b.photo_url)",
        "esc(b.booking_ref)",
        "esc(customer)",
        "esc(s.name)",
        "esc(s.description",
        "esc(r.open_time)",
        "esc(r.close_time)",
        "esc(initials(b.name))",
        "esc(b.service_name",
        "esc(b.barber_name",
    ):
        assert escaped in js, f"untrusted field not escaped: {escaped}"

    # CSP forbids inline event handlers → no inline handlers in the HTML shell.
    html = (PANEL_DIR / "index.html").read_text(encoding="utf-8")
    assert " onerror=" not in html
    assert " onclick=" not in html
    assert " javascript:" not in html
