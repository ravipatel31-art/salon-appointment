"""Application settings via pydantic-settings (env / .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Salon API"
    environment: str = "development"

    # Runtime database: PostgreSQL only (psycopg3 driver).
    database_url: str = "postgresql+psycopg://salon:salon@localhost:5432/salon"

    # Auth (used from phase 1)
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h

    # Seed admin (phase 1)
    admin_phone: str = ""
    admin_password: str = ""

    # Booking policy constants (AGENTS.md)
    booking_hold_minutes: int = 12
    cancel_refund_window_hours: int = 2

    # CORS — comma-separated origins, e.g.
    # ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
    # Unset → development allows all origins ("*"); production falls back to
    # an empty list (same-origin only, no CORS headers for other origins).
    allowed_origins: str = ""

    # Razorpay credentials (read by salon-integration's services/payments.py).
    # Kept here so integration does not need to edit config.py.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Seed admin email fallback (phone/password come from ADMIN_PHONE / ADMIN_PASSWORD).
    admin_email: str = "admin@salon.local"
    admin_name: str = "Salon Admin"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_allow_origins(self) -> list[str]:
        """Effective CORS allow-list for CORSMiddleware.

        - Explicit ``ALLOWED_ORIGINS`` (comma-separated) always wins.
        - Unset + ``ENVIRONMENT=development`` → ``["*"]`` (local Flutter web /
          Chrome dev servers, any port).
        - Unset + production → ``[]`` (same-origin only).
        """
        explicit = [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]
        if explicit:
            return explicit
        if self.environment.strip().lower() == "development":
            return ["*"]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
