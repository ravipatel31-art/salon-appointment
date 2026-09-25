"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import admin, auth, bookings, catalog, health
from app.config import get_settings

# Admin browser dashboard (phase 13, CONTRACT §Admin browser dashboard):
# same-origin vanilla SPA served from backend/app/static/panel/.
PANEL_DIR = Path(__file__).resolve().parent / "static" / "panel"

# Phase 14 — SQL-injection hardening / browser hardening for /panel responses.
# - default-src 'self' keeps the SPA's own /panel/app.css + /panel/app.js.
# - img-src https: because CONTRACT §Imagery allows absolute HTTPS photo_url
#   portraits (and the create-form preview) from other origins.
# - frame-ancestors 'none' blocks clickjacking of the admin panel.
PANEL_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' https: data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
PANEL_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": PANEL_CSP,
}


def _panel_file(path: Path) -> FileResponse:
    """FileResponse for panel assets with the hardening headers attached."""
    return FileResponse(path, headers=PANEL_SECURITY_HEADERS)


def _mount_panel(app: FastAPI) -> None:
    """Serve GET /panel (index) + /panel/{path} with SPA fallback.

    Existing files (app.css, app.js, …) are returned as-is (FileResponse —
    StaticFiles-equivalent serving of same-origin assets); anything else
    falls back to index.html so the client-side PATH routes
    (/panel/login, /panel/dashboard, /panel/barbers/{id}/edit,
    /panel/services/new, …) and deep links keep working (phase 15 — the
    server cannot see the sessionStorage session, so the /panel →
    /panel/login | /panel/dashboard choice is made client-side).
    Registered only under /panel so /docs, /health and API routers are
    untouched. Every /panel response carries nosniff + CSP (phase 14).
    """
    if not PANEL_DIR.is_dir():  # pragma: no cover - packaging guard
        return
    panel_root = PANEL_DIR.resolve()

    @app.get("/panel", include_in_schema=False)
    def panel_index() -> FileResponse:
        return _panel_file(panel_root / "index.html")

    @app.get("/panel/{path:path}", include_in_schema=False)
    def panel_fallback(path: str) -> FileResponse:
        if path:
            candidate = (panel_root / path).resolve()
            try:
                candidate.relative_to(panel_root)
            except ValueError:
                candidate = None  # path traversal attempt → SPA index
            if candidate is not None and candidate.is_file():
                return _panel_file(candidate)
        return _panel_file(panel_root / "index.html")



def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
    )
    # CORS — env-configurable via ALLOWED_ORIGINS (see app.config.Settings).
    # development default allows all origins; production requires an explicit
    # allow-list (empty list → same-origin only).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(bookings.router)
    app.include_router(admin.router)
    # Razorpay webhook — owned by salon-integration (app/api/webhooks.py),
    # wired here per that module's contract note.
    try:
        from app.api.webhooks import router as webhooks_router

        app.include_router(webhooks_router)
    except ImportError:  # pragma: no cover — integration module not present yet
        pass
    # Admin browser dashboard (phase 13) — static SPA under /panel.
    _mount_panel(app)
    return app


app = create_app()
