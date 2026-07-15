"""
app/core/config.py

Environment-driven application settings, loaded once via a cached Settings
instance. No secrets or connection strings are hardcoded anywhere else in
the codebase.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SLOT_DURATION_MINUTES = 30
DEFAULT_BOOKING_LEAD_TIME_MINUTES = 60


class Settings(BaseSettings):
    """Application configuration sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic"
    environment: str = "development"

    slot_duration_minutes: int = DEFAULT_SLOT_DURATION_MINUTES
    booking_lead_time_minutes: int = DEFAULT_BOOKING_LEAD_TIME_MINUTES

    auth_token_seed: str = "dev-only-insecure-seed-change-in-production"

    log_level: str = "INFO"

    app_title: str = "Clinic Booking API"
    app_description: str = "Backend API for booking, cancelling, and rescheduling clinic appointments."
    app_version: str = "0.1.0"

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        """Railway (and most managed Postgres providers) hand out a plain
        postgresql:// URL. SQLAlchemy defaults that to the sync psycopg2
        driver, which this project never installs — normalize to the
        async driver regardless of what the platform provides."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
