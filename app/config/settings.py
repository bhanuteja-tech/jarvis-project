"""Environment-based application configuration.

Values are loaded from process environment variables and an optional `.env`
file located at the repository root. No secrets may ever be hardcoded here;
see `.env.example` for the expected variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
DEFAULT_LEVER_BASE_URL = "https://api.lever.co/v0/postings"
DEFAULT_SEARCHAPI_SEARCH_URL = "https://www.searchapi.io/api/v1/search"


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

    #: SearchApi key. Held as SecretStr so it never renders in logs/reprs.
    #: Sent only as an Authorization Bearer header, never a query parameter.
    searchapi_search_url: str = DEFAULT_SEARCHAPI_SEARCH_URL
    searchapi_api_key: SecretStr = SecretStr("")
    searchapi_timeout_seconds: float = Field(default=30.0, gt=0)
    # Retries consume paid quota; keep the default conservative.
    searchapi_max_retries: int = Field(default=2, ge=0, le=10)
    searchapi_max_pages: int = Field(default=5, ge=1, le=50)

    career_fetch_timeout_seconds: float = Field(default=20.0, gt=0)
    career_max_attempts: int = Field(default=2, ge=1, le=10)
    career_max_bytes: int = Field(default=2_000_000, ge=10_000)
    career_max_redirects: int = Field(default=5, ge=0, le=10)
    #: Correction #2: HTTP is REJECTED by default; only HTTPS is fetched.
    #: Enabling this flag permits plain HTTP for controlled environments.
    career_allow_http: bool = False
    #: Correction #3: when robots.txt is unavailable/unreachable, `strict`
    #: (default) rejects the fetch; `permissive` proceeds with a warning.
    career_robots_permissive: bool = False
    career_robots_timeout_seconds: float = Field(default=5.0, gt=0)
    career_politeness_seconds: float = Field(default=2.0, ge=0)
    #: Layer-4 browser rendering stays OFF unless explicitly enabled AND the
    #: optional `playwright` extra is installed.
    career_browser_enabled: bool = False

    # --- Phase 2: JD understanding -----------------------------------------
    #: Analyze only the top-K ranked jobs (cost control).
    jd_top_k: int = Field(default=10, ge=1, le=500)
    #: Hard cap for a single JD's analyzed text.
    jd_max_chars: int = Field(default=20_000, ge=1_000)
    #: Optional semantic enhancement stage. OFF by default; requires a client
    #: implementing the JdLlmClient protocol to be supplied by wiring.
    jd_llm_enabled: bool = False

    # --- Phase 3: Candidate / resume intelligence ---------------------------
    #: Hard cap for a single resume's analyzed text (no truncation: oversize
    #: inputs FAIL with max_chars_violation).
    candidate_max_chars: int = Field(default=30_000, ge=1_000)
    #: When True, quarantined contact/PII values are stripped from the built
    #: profile after construction; ``redacted`` is set on the profile.
    candidate_redact_pii: bool = False

    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("greenhouse_base_url", "lever_base_url", "searchapi_search_url")
    @classmethod
    def _validate_source_base_url(cls, value: str) -> str:
        stripped = value.rstrip("/")
        if not stripped.startswith("https://"):
            raise ValueError("source base urls must use https")
        return stripped


@lru_cache
def get_settings() -> Settings:
    return Settings()
