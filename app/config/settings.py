"""Environment-based application configuration.

Values are loaded from process environment variables and an optional `.env`
file located at the repository root. No secrets may ever be hardcoded here;
see `.env.example` for the expected variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
DEFAULT_LEVER_BASE_URL = "https://api.lever.co/v0/postings"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/jarvis",
        description="SQLAlchemy URL for the primary PostgreSQL database.",
    )

    greenhouse_base_url: str = DEFAULT_GREENHOUSE_BASE_URL
    greenhouse_timeout_seconds: float = Field(default=30.0, gt=0)
    greenhouse_max_retries: int = Field(default=3, ge=0, le=10)
    greenhouse_board_registry_path: Path | None = None

    lever_base_url: str = DEFAULT_LEVER_BASE_URL
    lever_timeout_seconds: float = Field(default=30.0, gt=0)
    lever_max_retries: int = Field(default=3, ge=0, le=10)
    lever_page_size: int = Field(default=50, ge=1, le=100)
    lever_max_pages: int = Field(default=200, ge=1)
    lever_site_registry_path: Path | None = None

    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("greenhouse_base_url", "lever_base_url")
    @classmethod
    def _validate_source_base_url(cls, value: str) -> str:
        stripped = value.rstrip("/")
        if not stripped.startswith("https://"):
            raise ValueError("source base urls must use https")
        return stripped


@lru_cache
def get_settings() -> Settings:
    return Settings()
