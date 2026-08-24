"""Provider-agnostic LLM client layer for the Jarvis assistant surface.

Architecture:
    app/llm/base.py               protocol + typed errors (no vendor code)
    app/llm/openai_compatible.py  shared Chat-Completions wire format
    app/llm/{ollama,openai,...}.py  thin vendor adapters
    app/llm/catalog.py            configured-provider + capability registry
    app/llm/router.py             Phase 10B selection / fallback (no HTTP)
    app/llm/__init__.py           create_assistant_llm(settings) factory

Layering rules:
    - ``app.llm`` imports nothing from ``app.jarvis`` or the graph.
    - Callers see ONLY ``AssistantLlmClient``; provider specifics never leak.
    - Every network-capable method raises typed LLMProviderError subclasses;
      raw httpx exceptions never escape this package.

The deterministic system is the default: when the master flag is off the
factory returns a DisabledAssistantLlmClient and NOTHING in this package
performs I/O. Routing is also OFF by default and never probes the network
just to discover providers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from app.config.settings import Settings
from app.llm.catalog import KNOWN_PROVIDERS, build_provider_client, configured_provider_names

__all__ = ["create_assistant_llm"]


@runtime_checkable
class AssistantClientProtocol(Protocol):
    """The ONLY interface the rest of the application may depend on."""

    enabled: bool
    model_name: str

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str: ...

    def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]: ...

    async def health(self) -> dict[str, Any]: ...


def create_assistant_llm(
    settings: Settings,
    *,
    transports: dict[str, Any] | None = None,
    client_builders: dict[str, Any] | None = None,
) -> Any:
    """Factory returning the configured provider client (or a routing wrapper).

    Returns a disabled client whenever: the master flag is off, the provider
    name is unknown (routing off), required credentials are missing, or
    routing is on but no provider is configured. In those states no method
    will attempt network I/O.
    """
    if not settings.jarvis_assistant_llm_enabled:
        from app.llm.base import DisabledAssistantClient

        return DisabledAssistantClient(reason="assistant LLM disabled by configuration")

    if settings.jarvis_llm_routing_enabled:
        from app.llm.base import DisabledAssistantClient
        from app.llm.router import LlmRouter, RoutingAssistantClient

        if not configured_provider_names(settings):
            return DisabledAssistantClient(reason="no configured LLM providers for routing")
        return RoutingAssistantClient(
            settings,
            router=LlmRouter(settings),
            transports=transports,
            client_builders=client_builders,
        )

    provider = (settings.jarvis_llm_provider or "").strip().lower()
    if provider not in KNOWN_PROVIDERS:
        from app.llm.base import DisabledAssistantClient

        return DisabledAssistantClient(reason=f"unknown provider {provider!r}")

    from app.llm.base import DisabledAssistantClient
    from app.llm.catalog import is_provider_configured

    if not is_provider_configured(provider, settings):
        return DisabledAssistantClient(reason=f"{provider} is not configured")

    transport = (transports or {}).get(provider)
    return build_provider_client(provider, settings, transport=transport)
