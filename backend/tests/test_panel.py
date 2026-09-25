"""Phase 13/14/15 — admin browser dashboard SPA served at GET /panel.

Asserts:
- /panel returns 200 HTML (index.html) and references local assets.
- Assets (app.css / app.js) resolve same-origin with sensible types.
- SPA fallback: unknown /panel/{path} → index.html.
- Path traversal cannot escape backend/app/static/panel/.
- Existing routes (/docs, /health, /openapi.json) are untouched.
- Phase 14: nosniff + CSP hardening headers on /panel*, full-page editor
  markup (Back control), and app.js syntax under node.
- Phase 15: separate login page + dashboard page as PATH routes —
  /panel/login and /panel/dashboard return 200 HTML through the SPA
  fallback (they are not files), every other panel path serves the shell,
  and app.js navigates with history.pushState/popstate (no hash router).
- Phase 16: app logo — GET /panel/logo.svg (+ .png) serve image/*
  same-origin, login shows it large, the topbar brand slot shows it
  small, and the favicon points at the same asset.
"""

from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "panel"


def test_panel_dir_has_spa_assets():
    assert (PANEL_DIR / "index.html").is_file()
    assert (PANEL_DIR / "app.css").is_file()
    assert (PANEL_DIR / "app.js").is_file()


def test_panel_index_returns_html(client):
    resp = client.get("/panel")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "<title>" in body
    # SPA shell markers: login + admin tabs
    assert 'id="login-view"' in body
    assert 'id="shell-view"' in body
    assert 'data-tab="barbers"' in body
    assert 'data-tab="services"' in body
    assert 'data-tab="bookings"' in body
    assert 'data-tab="dashboard"' in body
    # Same-origin assets — no external CDN for core UI
    assert "/panel/app.css" in body
    assert "/panel/app.js" in body
    assert 'src="http' not in body and 'href="http' not in body


def test_panel_assets_resolve(client):
    css = client.get("/panel/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    # brand colours per contract
    assert "#7A2E4A" in css.text
    assert "#B08D57" in css.text

    js = client.get("/panel/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    # sessionStorage token + admin-only handling + existing APIs only
    assert "sessionStorage" in js.text
    assert "/auth/login" in js.text
    assert "/admin/barbers" in js.text
    assert "/admin/services" in js.text
    assert "/admin/bookings" in js.text
    assert "/admin/dashboard" in js.text
    assert "admin_only" in js.text or "Admin only" in js.text


def test_panel_spa_fallback(client):
    resp = client.get("/panel/barbers/anything")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'id="login-view"' in resp.text


def test_panel_path_traversal_blocked(client):
    # Encoded ../ must not leak files outside the panel directory.
    resp = client.get("/panel/..%2f..%2fapp%2fconfig.py")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "class Settings" not in resp.text
    assert "DATABASE_URL" not in resp.text


def test_existing_routes_unaffected(client):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    # Panel routes are excluded from the OpenAPI schema (include_in_schema=False)
    import json

    schema = json.loads(client.get("/openapi.json").text)
    assert not any(p.startswith("/panel") for p in schema.get("paths", {}))
    # Public catalog still works
    assert client.get("/services").status_code == 200
    assert client.get("/barbers").status_code == 200


# ─────────────────────── phase 14 — full-page edits + hardening ───────────────────────


def test_panel_security_headers(client):
    """nosniff + CSP (default-src 'self', frame-ancestors 'none') on /panel*."""
    for url in ("/panel", "/panel/app.css", "/panel/app.js", "/panel/whatever"):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert resp.headers.get("x-content-type-options") == "nosniff", url
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp, csp
        assert "frame-ancestors 'none'" in csp, csp
        assert "script-src 'self'" in csp, csp
        # third-party portraits (CONTRACT §Imagery) still allowed
        assert "img-src" in csp and "https:" in csp, csp
    # API responses (non-panel) are untouched by the panel header policy
    assert "content-security-policy" not in client.get("/health").headers


def test_panel_path_routes_present():
    """Edit opens a dedicated path route; Back control returns to the list.

    Phase 15 — hash routing (#/…) is replaced by real paths driven by
    history.pushState / popstate; login and dashboard are separate pages.
    """
    js = (PANEL_DIR / "app.js").read_text(encoding="utf-8")
    html = (PANEL_DIR / "index.html").read_text(encoding="utf-8")

    # router wiring — path navigation, no hash fragments left
    assert "popstate" in js
    assert "pushState" in js
    assert "hashchange" not in js
    assert "location.hash" not in js
    assert "#/" not in js

    # every phase-15 URL is a real path
    for path in (
        '"/panel/login"',
        '"/panel/dashboard"',
        '"/panel/barbers/new"',
        '"/panel/services/new"',
        "`/panel/barbers/${b.id}/edit`",
        "`/panel/services/${s.id}/edit`",
        "`/panel/barbers/${created.id}/edit`",
        "`/panel/services/${created.id}/edit`",
        '"/panel/" + btn.dataset.tab',   # tabs are path routes too
        '"/panel/" + btn.dataset.back',  # Back control on edit pages
    ):
        assert path in js, f"missing path route: {path}"
    assert 'btn.dataset.back' in js
    # unauthenticated → login page; sign-in / log out → dashboard / login
    assert 'redirect(LOGIN_PATH)' in js
    assert "redirect(DASH_PATH)" in js

    # full-page editor sections (not modals)
    assert 'id="page-barber-edit"' in html
    assert 'id="page-service-edit"' in html
    assert 'data-back="barbers"' in html
    assert 'data-back="services"' in html
    # barber fields + weekly schedule share the same page
    assert 'id="barber-form"' in html
    assert 'id="schedule-form"' in html
    assert html.index('id="barber-form"') < html.index('id="page-service-edit"')
    # edit modals from phase 13 are gone (delete/complete stay modal)
    assert 'id="barber-modal"' not in html
    assert 'id="service-modal"' not in html
    assert 'id="schedule-modal"' not in html
    assert 'id="complete-modal"' in html

    # no CDN / external scripts (contract: local assets only)
    assert 'src="http' not in html and 'href="http' not in html


def test_panel_login_and_dashboard_routes(client):
    """Phase 15 — /panel/login and /panel/dashboard are 200 HTML pages.

    Neither is a real file: both resolve through the server SPA fallback
    (GET /panel/{path:path} → index.html) with the phase-14 hardening
    headers. The login page ships with the admin shell hidden (its own
    page — no tabs) and the shell markup for the dashboard page.
    """
    for url in ("/panel/login", "/panel/dashboard"):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert "text/html" in resp.headers["content-type"], url
        body = resp.text
        assert "<title>" in body, url
        assert 'id="login-view"' in body, url          # login page markup
        assert 'id="shell-view"' in body, url          # dashboard shell markup
        assert "/panel/app.css" in body and "/panel/app.js" in body, url
        # phase-14 hardening unchanged on the new routes
        assert resp.headers.get("x-content-type-options") == "nosniff", url
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp, url
    # login page renders without tabs/shell visible before JS boots
    login = client.get("/panel/login").text
    assert '<div id="shell-view" class="shell-view" hidden>' in login
    # assets are real files — not swallowed by the fallback
    assert client.get("/panel/app.js").status_code == 200
    assert client.get("/panel/app.css").status_code == 200


def test_panel_hidden_wins_over_display_rules():
    """`hidden` must beat component display rules (phase 15 rendering).

    .login-view / .shell-view set `display:flex`, which as an author rule
    outranks the UA `[hidden]{display:none}` — without an explicit rule the
    admin shell (topbar + tabs) would render *on* the login page and the
    login card would stay on the dashboard after sign-in, breaking
    "login page only (no tabs/shell)".
    """
    css = (PANEL_DIR / "app.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css
    # the two competing display rules that made `hidden` a no-op
    assert ".login-view {" in css and "display: flex" in css
    assert ".shell-view { min-height: 100vh; display: flex;" in css
    # shell + login start hidden in the markup (login page = no shell)
    html = (PANEL_DIR / "index.html").read_text(encoding="utf-8")
    assert '<div id="shell-view" class="shell-view" hidden>' in html
    assert '<div id="login-view" class="login-view">' in html


def test_panel_app_routes_serve_spa(client):
    """Every phase-15 path deep-links to the SPA shell (200 HTML)."""
    for url in (
        "/panel",
        "/panel/barbers",
        "/panel/barbers/new",
        "/panel/barbers/7/edit",
        "/panel/services",
        "/panel/services/new",
        "/panel/services/3/edit",
        "/panel/bookings",
        "/panel/dashboard",
    ):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert "text/html" in resp.headers["content-type"], url
        assert 'id="login-view"' in resp.text, url
        assert 'id="shell-view"' in resp.text, url


def test_panel_js_syntax():
    """app.js parses under node when available (skipped otherwise)."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:  # pragma: no cover - environment without node
        import pytest

        pytest.skip("node not available")
    result = subprocess.run(
        [node, "--check", str(PANEL_DIR / "app.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ─────────────────────── phase 16 — panel app logo ───────────────────────


def test_panel_logo_assets_serve_images(client):
    """GET /panel/logo.svg and GET /panel/logo.png → 200 image/*.

    Both live in backend/app/static/panel/ and are served same-origin by
    the SPA fallback file branch, so CSP `img-src 'self'` covers them
    without any CDN. The SVG carries the wine/gold brand colours.
    """
    svg = client.get("/panel/logo.svg")
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers["content-type"]
    assert svg.headers.get("x-content-type-options") == "nosniff"
    csp = svg.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "img-src 'self'" in csp and "https:" in csp
    assert svg.text.lstrip().startswith("<svg")
    assert "#7A2E4A" in svg.text and "#B08D57" in svg.text  # wine · gold

    png = client.get("/panel/logo.png")
    assert png.status_code == 200
    assert "image/png" in png.headers["content-type"]
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert (PANEL_DIR / "logo.svg").is_file()
    assert (PANEL_DIR / "logo.png").is_file()


def test_panel_login_and_topbar_show_logo(client):
    """Login page shows the logo large; topbar brand shows it small."""
    body = client.get("/panel/login").text
    # large mark above the brand title on /panel/login (alt = product name)
    assert '<img class="login-logo" src="/panel/logo.svg" alt="Salon"' in body
    # small mark in the topbar brand slot of the authenticated shell
    assert '<img class="brand-logo" src="/panel/logo.svg" alt="Salon"' in body
    # the old ✦ text glyph is gone
    assert "logo-mark" not in body
    # favicon → same same-origin asset
    assert 'rel="icon"' in body
    assert 'href="/panel/logo.svg"' in body
    # no external / data image hosts (CSP img-src 'self' + local assets)
    assert 'src="http' not in body and 'href="http' not in body
    assert "src=\"data:" not in body


def test_panel_logo_css_sizes():
    """CSS renders the login logo large and the topbar logo small."""
    css = (PANEL_DIR / "app.css").read_text(encoding="utf-8")
    assert ".login-logo {" in css and "width: 104px" in css
    assert ".brand-logo {" in css and "width: 34px" in css
    # brand palette untouched
    assert "#7A2E4A" in css and "#B08D57" in css
