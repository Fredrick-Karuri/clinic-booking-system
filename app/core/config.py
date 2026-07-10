"""
app/core/config.py

Environment-driven application settings, loaded once via a cached Settings
instance. No secrets or connection strings are hardcoded anywhere else in
the codebase.
"""

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()