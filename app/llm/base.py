"""Provider-agnostic client protocol + typed error taxonomy.

No vendor code lives here. Providers translate their wire errors into the
typed exceptions below; raw HTTP/network exceptions must never escape
``app.llm``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


class LLMProviderError(Exception):
    """Base class: carries a stable machine ``code`` + safe user message."""

    code = "provider_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class LLMConfigurationError(LLMProviderError):
    """Invalid provider settings (scheme, HTTPS policy, missing endpoint)."""

    code = "configuration_error"


class ProviderUnavailableError(LLMProviderError):
    code = "provider_unavailable"


class LLMTimeoutError(LLMProviderError):
    code = "timeout"


class AuthenticationFailedError(LLMProviderError):
    code = "authentication_failed"


class InvalidModelError(LLMProviderError):
    code = "invalid_model"


class InvalidResponseError(LLMProviderError):
    code = "invalid_response"


class RateLimitedError(LLMProviderError):
    code = "rate_limited"


class ProviderHTTPError(LLMProviderError):
    code = "provider_error"


class DisabledAssistantClient:
    """Default no-op client. Never performs I/O; every use raises."""

    enabled = False

    def __init__(self, *, reason: str = "assistant LLM disabled") -> None:
        self.reason = reason

    @property
    def model_name(self) -> str:
        return ""

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        raise ProviderUnavailableError(self.reason)

    async def stream(  # type: ignore[override] - async generator form
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        raise ProviderUnavailableError(self.reason)
        yield ""  # pragma: no cover - makes this an async generator

    async def health(self) -> dict[str, Any]:
        return {
            "reachable": False,
            "model": "",
            "model_available": False,
            "reason": self.reason,
            "status": "not_configured",
        }


@runtime_checkable
class AssistantClientProtocol(Protocol):
    """Structural interface for any provider adapter."""

    enabled: bool
    model_name: str

    async def generate(
        self, *, system_prompt: str, user_prompt: str, json_mode: bool = False
    ) -> str: ...

    def stream(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]: ...

    async def health(self) -> dict[str, Any]: ...


def safe_status(
    enabled: bool,
    provider: str,
    model: str,
    reachable: bool,
    *,
    routing_enabled: bool = False,
    configured_providers: list[str] | None = None,
    capabilities: list[str] | None = None,
    model_available: bool = False,
    health_status: str = "",
) -> dict[str, Any]:
    """The ONLY shape /api/llm/status may return — metadata, never secrets."""
    return {
        "enabled": bool(enabled),
        "provider": provider if enabled else "",
        "model": model if enabled else "",
        "reachable": bool(reachable),
        "routing_enabled": bool(routing_enabled) if enabled else False,
        "configured_providers": list(configured_providers or []) if enabled else [],
        "capabilities": list(capabilities or []) if enabled else [],
        "model_available": bool(model_available) if enabled else False,
        "health_status": (health_status or "") if enabled else "",
    }


__all__ = [
    "AssistantClientProtocol",
    "AuthenticationFailedError",
    "DisabledAssistantClient",
    "InvalidModelError",
    "InvalidResponseError",
    "LLMConfigurationError",
    "LLMProviderError",
    "LLMTimeoutError",
    "ProviderHTTPError",
    "ProviderUnavailableError",
    "RateLimitedError",
    "safe_status",
]
