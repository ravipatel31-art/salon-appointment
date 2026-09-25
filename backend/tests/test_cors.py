"""CORS wiring (transport concern — not part of docs/CONTRACT.md).

Covers:
- Settings resolution: explicit ALLOWED_ORIGINS > development allow-all >
  production empty list (same-origin only).
- CORSMiddleware behaviour on the app: credentials, methods, headers.
"""

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import create_app

# --- Settings resolution -----------------------------------------------------


def test_development_default_allows_all_origins() -> None:
    s = Settings(_env_file=None)
    assert s.environment == "development"  # field default
    assert s.cors_allow_origins == ["*"]


def test_production_without_allowed_origins_is_empty() -> None:
    s = Settings(_env_file=None, environment="production", allowed_origins="")
    assert s.cors_allow_origins == []


def test_explicit_allowed_origins_parsing() -> None:
    s = Settings(
        _env_file=None,
        environment="production",
        allowed_origins=" https://a.example , ,https://b.example,",
    )
    assert s.cors_allow_origins == ["https://a.example", "https://b.example"]


def test_explicit_allowed_origins_win_in_development() -> None:
    s = Settings(
        _env_file=None,
        environment="development",
        allowed_origins="http://localhost:5173",
    )
    assert s.cors_allow_origins == ["http://localhost:5173"]


# --- Middleware on the (development-default) app -----------------------------


def test_dev_app_simple_request_allows_any_origin() -> None:
    client = TestClient(create_app())
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] in (
        "*",
        "http://localhost:5173",
    )


def test_dev_app_preflight_methods_headers_credentials() -> None:
    client = TestClient(create_app())
    resp = client.options(
        "/bookings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    allow_methods = resp.headers["access-control-allow-methods"]
    for method in ("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"):
        assert method in allow_methods
    assert resp.headers["access-control-allow-credentials"] == "true"
    allow_headers = resp.headers["access-control-allow-headers"].lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


# --- Production behaviour (fresh app with patched settings) ------------------


def test_production_app_denies_unlisted_origin(monkeypatch) -> None:
    prod = Settings(_env_file=None, environment="production", allowed_origins="")
    monkeypatch.setattr(main_module, "get_settings", lambda: prod)
    client = TestClient(main_module.create_app())
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_production_app_allows_configured_origin(monkeypatch) -> None:
    prod = Settings(
        _env_file=None,
        environment="production",
        allowed_origins="https://salon.example",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: prod)
    client = TestClient(main_module.create_app())
    resp = client.get("/health", headers={"Origin": "https://salon.example"})
    assert resp.headers["access-control-allow-origin"] == "https://salon.example"
