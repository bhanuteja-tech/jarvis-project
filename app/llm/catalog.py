"""Provider catalog: configuration checks, models, and capability metadata.

Capabilities are derived from the Phase 10A adapters as they exist today —
not from marketing claims or unimplemented wire options.

- ``streaming``: adapter yields genuine provider deltas from ``stream()``.
- ``structured_output``: adapter sends a native JSON response format when
  ``json_mode=True`` (OpenAI-compatible ``response_format``). Ollama, Gemini
  and Anthropic accept the flag but do not change the wire payload.
- ``reasoning``: same Chat/Messages adapter can target a reasoning model
  family (DeepSeek reasoner, Anthropic Claude).
- ``local_private``: inference can stay on an operator-controlled host
  (Ollama). Cloud vendors are never tagged local.
- ``long_context``: default configured model family is a long-context SKU
  (Gemini, Moonshot Kimi).
- ``general``: ordinary chat completions / messages (all adapters).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings

KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {
        "ollama",
        "openai",
        "openrouter",
        "deepseek",
        "moonshot",
        "gemini",
        "anthropic",
    }
)

# Relative config tiers only — not prices, not token accounting.
# cost_tier / latency_tier: 1 = lowest, 3 = highest.
_COST_LOW = 1
_COST_MID = 2
_COST_HIGH = 3
_LAT_LOW = 1
_LAT_MID = 2


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    capabilities: frozenset[str]
    cost_tier: int
    latency_tier: int
    credential_attr: str | None
    """Settings SecretStr attribute required to treat the provider as configured.
    ``None`` means no API key (Ollama)."""


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        name="ollama",
        capabilities=frozenset(
            {"streaming", "local_private", "general", "intent", "narration", "chat"}
        ),
        cost_tier=_COST_LOW,
        latency_tier=_LAT_MID,
        credential_attr=None,
    ),
    "openai": ProviderSpec(
        name="openai",
        capabilities=frozenset(
            {
                "streaming",
                "structured_output",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_HIGH,
        latency_tier=_LAT_MID,
        credential_attr="openai_api_key",
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        capabilities=frozenset(
            {
                "streaming",
                "structured_output",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_MID,
        latency_tier=_LAT_MID,
        credential_attr="openrouter_api_key",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        capabilities=frozenset(
            {
                "streaming",
                "structured_output",
                "reasoning",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_LOW,
        latency_tier=_LAT_MID,
        credential_attr="deepseek_api_key",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        capabilities=frozenset(
            {
                "streaming",
                "structured_output",
                "long_context",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_MID,
        latency_tier=_LAT_MID,
        credential_attr="moonshot_api_key",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        capabilities=frozenset(
            {
                "streaming",
                "long_context",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_LOW,
        latency_tier=_LAT_LOW,
        credential_attr="gemini_api_key",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        capabilities=frozenset(
            {
                "streaming",
                "reasoning",
                "general",
                "intent",
                "narration",
                "chat",
            }
        ),
        cost_tier=_COST_HIGH,
        latency_tier=_LAT_MID,
        credential_attr="anthropic_api_key",
    ),
}

TASK_REQUIRED_CAPABILITIES: dict[str, frozenset[str]] = {
    "intent": frozenset(),
    "narration": frozenset(),
    "chat": frozenset(),
    "reasoning": frozenset({"reasoning"}),
    "structured_json": frozenset({"structured_output"}),
    "streaming": frozenset({"streaming"}),
}


def parse_provider_list(raw: str) -> list[str]:
    """Split a comma-separated provider list; drop unknowns and duplicates."""
    seen: set[str] = set()
    ordered: list[str] = []
    for part in (raw or "").split(","):
        name = part.strip().lower()
        if not name or name not in KNOWN_PROVIDERS or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def explicit_provider_names(settings: Settings) -> list[str]:
    """Providers named in 10A/10B selector settings (order preserved)."""
    chunks = [
        settings.jarvis_llm_provider,
        settings.jarvis_llm_routing_default,
        settings.jarvis_llm_fallback_providers,
    ]
    merged = ",".join(str(c or "") for c in chunks)
    return parse_provider_list(merged)


def _secret_configured(settings: Settings, attr: str) -> bool:
    value = getattr(settings, attr)
    raw = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
    return bool(str(raw).strip())


def is_provider_configured(name: str, settings: Settings) -> bool:
    """True when the provider may be instantiated from current settings.

    Cloud vendors require a non-empty API key. Ollama has no required key and
    is configured only when explicitly named (provider / routing default /
    fallback) or when ``OLLAMA_API_KEY`` is set for a protected tunnel.
    Unknown names are never configured.
    """
    spec = PROVIDER_SPECS.get((name or "").strip().lower())
    if spec is None:
        return False
    if spec.credential_attr:
        return _secret_configured(settings, spec.credential_attr)
    # ollama
    if _secret_configured(settings, "ollama_api_key") or _secret_configured(
        settings, "ollama_auth_token"
    ):
        return True
    return spec.name in set(explicit_provider_names(settings))


def configured_provider_names(settings: Settings) -> list[str]:
    """Configured providers: explicit names first, then remaining keyed vendors."""
    ordered: list[str] = []
    seen: set[str] = set()
    for name in explicit_provider_names(settings):
        if is_provider_configured(name, settings) and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in sorted(PROVIDER_SPECS):
        if name in seen:
            continue
        if is_provider_configured(name, settings):
            ordered.append(name)
            seen.add(name)
    return ordered


def model_for_provider(name: str, settings: Settings) -> str:
    generic = (settings.jarvis_llm_model or "").strip()
    if name == "deepseek":
        return (settings.deepseek_model or "").strip() or generic
    if name == "moonshot":
        return (settings.moonshot_model or "").strip() or generic
    if name == "gemini":
        return (settings.gemini_model or "").strip() or generic
    if name == "anthropic":
        return (settings.anthropic_model or "").strip() or generic
    if name == "ollama":
        return generic or (settings.ollama_model or "").strip()
    return generic


def build_provider_client(
    name: str,
    settings: Settings,
    *,
    transport: object | None = None,
) -> object:
    """Instantiate a Phase 10A adapter. Caller must ensure the name is known."""
    key = (name or "").strip().lower()
    kwargs = {}
    if transport is not None:
        kwargs["transport"] = transport
    if key == "ollama":
        from app.llm.ollama import OllamaClient

        return OllamaClient(settings, **kwargs)
    if key == "openai":
        from app.llm.openai import OpenAIClient

        return OpenAIClient(settings, **kwargs)
    if key == "openrouter":
        from app.llm.openrouter import OpenRouterClient

        return OpenRouterClient(settings, **kwargs)
    if key == "deepseek":
        from app.llm.deepseek import DeepSeekClient

        return DeepSeekClient(settings, **kwargs)
    if key == "moonshot":
        from app.llm.moonshot import MoonshotClient

        return MoonshotClient(settings, **kwargs)
    if key == "gemini":
        from app.llm.gemini import GeminiClient

        return GeminiClient(settings, **kwargs)
    if key == "anthropic":
        from app.llm.anthropic import AnthropicClient

        return AnthropicClient(settings, **kwargs)
    raise ValueError(f"unknown provider {name!r}")


__all__ = [
    "KNOWN_PROVIDERS",
    "PROVIDER_SPECS",
    "ProviderSpec",
    "TASK_REQUIRED_CAPABILITIES",
    "build_provider_client",
    "configured_provider_names",
    "explicit_provider_names",
    "is_provider_configured",
    "model_for_provider",
    "parse_provider_list",
]
