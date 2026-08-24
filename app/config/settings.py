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
    #: Maximum raw resume upload size (PDF/DOCX/TXT/MD) accepted by the
    #: document-extraction layer. Checked BEFORE any parsing work.
    max_resume_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)

    # --- Phase 5: Resume tailoring ------------------------------------------
    #: Maximum kept highlights per tailored experience item.
    tailor_max_highlights: int = Field(default=3, ge=1, le=10)
    #: Maximum projects in the tailored resume.
    tailor_max_projects: int = Field(default=3, ge=0, le=20)
    #: Optional LLM bullet rewriting. OFF by default; requires a client
    #: implementing the TailoringLlmClient protocol. Every rewrite passes the
    #: token-subset truth guard or the original bullet is retained.
    tailoring_llm_enabled: bool = False

    # --- Phase 7: Jarvis product layer ---------------------------------------
    jarvis_max_concurrent_runs: int = Field(default=4, ge=1, le=64)
    jarvis_assistant_llm_enabled: bool = False
    jarvis_ws_path: str = "/ws/jarvis"
    #: Deterministic FIFO retention cap for completed-run stores (result +
    #: artifacts). Oldest runs are evicted; nothing is persisted.
    jarvis_max_stored_runs: int = Field(default=100, ge=1, le=10_000)
    #: Comma-separated extra origins accepted by the WS same-origin gate.
    #: Same-host and localhost origins are always allowed; empty Origin
    #: (non-browser clients) is allowed for tests and tooling.
    jarvis_ws_allow_origins: str = ""

    # --- Phase 10: LLM provider layer (Jarvis assistant surface ONLY) --------
    #: Provider selection. Unknown/missing config disables the layer.
    #: Supported: ollama | deepseek | moonshot | gemini | anthropic | openai | openrouter
    jarvis_llm_provider: str = "ollama"
    #: Model identifier exactly as the provider expects it. For OpenAI /
    #: OpenRouter this is THE model setting; vendor-specific defaults below
    #: apply to their own adapters when this is empty.
    jarvis_llm_model: str = ""
    #: Provider base URL override. Empty uses vendor defaults everywhere.
    jarvis_llm_base_url: str = ""
    jarvis_llm_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    jarvis_llm_max_tokens: int = Field(default=512, ge=1, le=8192)
    jarvis_llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    #: Emit `token` events from genuine provider deltas only.
    jarvis_llm_streaming: bool = False

    # --- Phase 10B: capability-aware routing (OFF by default) ----------------
    #: When false, ``create_assistant_llm`` returns the single Phase 10A client.
    jarvis_llm_routing_enabled: bool = False
    #: Preferred provider when routing is on and the request has no explicit
    #: preference. Empty falls back to ``jarvis_llm_provider``.
    jarvis_llm_routing_default: str = ""
    #: lowest | balanced | ignore  (config tiers only — no billing)
    jarvis_llm_cost_preference: str = "balanced"
    #: lowest | balanced | ignore
    jarvis_llm_latency_preference: str = "balanced"
    #: any | local  (local restricts the pool to Ollama)
    jarvis_llm_privacy_preference: str = "any"
    #: Comma-separated fallback order, e.g. ``openai,gemini``. Unknown names ignored.
    jarvis_llm_fallback_providers: str = ""
    #: Bound for /status health probes (seconds). Routing selection never probes.
    jarvis_llm_health_timeout_seconds: float = Field(default=3.0, ge=0.5, le=15.0)
    #: When True, non-loopback Ollama URLs must be HTTPS (ngrok/production).
    #: Loopback HTTP (127.0.0.1 / localhost) remains allowed for local development.
    jarvis_ollama_require_https: bool = False

    #: Server-side credentials ONLY (SecretStr never renders in logs/reprs).
    openai_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    #: OPTIONAL bearer token protecting a tunnel-exposed Ollama server.
    ollama_api_key: SecretStr = SecretStr("")

    # --- Additional providers (Phase 10 extension) ---------------------------
    #: DeepSeek — low-cost cloud provider, OpenAI-compatible wire format.
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    #: Moonshot Kimi — OpenAI-compatible wire format.
    moonshot_api_key: SecretStr = SecretStr("")
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    moonshot_model: str = "moonshot-v1-8k"

    #: Google Gemini — native generativelanguage API.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-2.0-flash"

    #: Anthropic Claude — native Messages API.
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-20250514"

    #: Ollama-specific configuration (aliases of the generic LLM_* vars so
    #: both naming styles work; generic values win when set).
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_auth_token: SecretStr = SecretStr("")

    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("jarvis_llm_cost_preference", "jarvis_llm_latency_preference")
    @classmethod
    def _normalize_llm_tier_preference(cls, value: str) -> str:
        normalized = (value or "balanced").strip().lower()
        allowed = {"lowest", "balanced", "ignore"}
        if normalized not in allowed:
            raise ValueError(f"preference must be one of {sorted(allowed)}")
        return normalized

    @field_validator("jarvis_llm_privacy_preference")
    @classmethod
    def _normalize_llm_privacy_preference(cls, value: str) -> str:
        normalized = (value or "any").strip().lower()
        allowed = {"any", "local"}
        if normalized not in allowed:
            raise ValueError(f"privacy preference must be one of {sorted(allowed)}")
        return normalized

    @field_validator("jarvis_llm_routing_default", "jarvis_llm_fallback_providers")
    @classmethod
    def _strip_routing_strings(cls, value: str) -> str:
        return (value or "").strip()

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
