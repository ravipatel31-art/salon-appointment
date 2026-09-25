from app.config import Settings, get_settings


def test_settings_defaults_to_postgres_url() -> None:
    """Runtime must target PostgreSQL (project rule) — check the field default."""
    default = Settings.model_fields["database_url"].default
    assert default.startswith("postgresql")


def test_get_settings_singleton() -> None:
    assert get_settings() is get_settings()


def test_booking_policy_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.booking_hold_minutes == 12
    assert s.cancel_refund_window_hours == 2
