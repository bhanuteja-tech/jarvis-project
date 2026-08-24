"""Ollama endpoint resolution for local development and remote HTTPS tunnels.

No HTTP lives here. The adapter uses these helpers to:
- pick JARVIS_LLM_BASE_URL over OLLAMA_BASE_URL over the loopback default
- strip trailing slashes
- enforce optional HTTPS for non-loopback hosts
- resolve the optional bearer token without exposing it
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.config.settings import Settings
from app.llm.base import LLMConfigurationError

_DEV_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def normalize_base_url(raw: str) -> str:
    return (raw or "").strip().rstrip("/")


def resolve_ollama_base_url(settings: Settings) -> str:
    """Prefer the generic LLM base URL, then the Ollama-specific alias."""
    generic = normalize_base_url(settings.jarvis_llm_base_url)
    if generic:
        return generic
    specific = normalize_base_url(settings.ollama_base_url)
    if specific:
        return specific
    return _DEV_DEFAULT_BASE_URL


def is_loopback_host(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower().strip("[]")
    return host in _LOOPBACK_HOSTS


def validate_ollama_base_url(url: str, *, require_https: bool) -> None:
    """Raise a typed configuration error for unusable endpoints.

    HTTPS URLs are never rewritten to HTTP. Loopback HTTP remains valid so
    local development keeps working when production HTTPS is required.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMConfigurationError("Ollama base URL is invalid")
    if parsed.scheme == "https":
        return
    if require_https and not is_loopback_host(parsed.hostname):
        raise LLMConfigurationError("Ollama base URL must use HTTPS")


def ollama_bearer_token(settings: Settings) -> str:
    """Server-side token only. Never log or return this value."""
    primary = settings.ollama_api_key.get_secret_value().strip()
    if primary:
        return primary
    return settings.ollama_auth_token.get_secret_value().strip()


def redact_secrets(message: str, settings: Settings) -> str:
    token = ollama_bearer_token(settings)
    if token and token in message:
        return message.replace(token, "[redacted]")
    return message


__all__ = [
    "is_loopback_host",
    "normalize_base_url",
    "ollama_bearer_token",
    "redact_secrets",
    "resolve_ollama_base_url",
    "validate_ollama_base_url",
]
