"""Capability-aware LLM routing (Phase 10B).

Selects and orders configured Phase 10A providers. Does not speak HTTP:
adapters remain the only components that contact vendors.

``decide()`` is a pure configuration function — it never probes the network.
Failure fallback happens at generate/stream time by walking ``fallback_chain``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from app.config.settings import Settings
from app.llm.base import LLMProviderError, ProviderUnavailableError
from app.llm.catalog import (
    PROVIDER_SPECS,
    TASK_REQUIRED_CAPABILITIES,
    build_provider_client,
    configured_provider_names,
    is_provider_configured,
    model_for_provider,
    parse_provider_list,
)

logger = logging.getLogger(__name__)

ClientBuilder = Callable[[str], Any]


@dataclass(frozen=True)
class RouteRequest:
    task: str = "chat"
    requires_streaming: bool = False
    requires_structured_output: bool = False
    preferred_provider: str | None = None
    privacy_preference: str | None = None
    cost_preference: str | None = None
    latency_preference: str | None = None


@dataclass(frozen=True)
class RouteDecision:
    provider: str
    model: str
    reason: str
    fallback_chain: tuple[str, ...]


def bind_assistant_task(client: Any, task: str) -> Any:
    """Return a task-bound view when the client is a router; otherwise ``client``."""
    binder = getattr(client, "bind_task", None)
    if callable(binder):
        return binder(task)
    return client


class LlmRouter:
    """Policy engine: configured providers × capabilities × preferences."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self._settings.jarvis_llm_routing_enabled)

    def configured_names(self) -> list[str]:
        return configured_provider_names(self._settings)

    def decide(self, request: RouteRequest | None = None) -> RouteDecision | None:
        """Pick a provider without performing I/O.

        Returns ``None`` when routing is disabled or no configured provider
        satisfies the request — callers then keep Phase 10A / deterministic
        behaviour.
        """
        if not self.enabled:
            return None
        req = request or RouteRequest()
        candidates = self._eligible(req)
        if not candidates:
            return None
        ordered = self._order(candidates, req)
        primary = ordered[0]
        reason = self._reason(primary, req, ordered)
        return RouteDecision(
            provider=primary,
            model=model_for_provider(primary, self._settings),
            reason=reason,
            fallback_chain=tuple(ordered[1:]),
        )

    def _required_caps(self, request: RouteRequest) -> frozenset[str]:
        task = (request.task or "chat").strip().lower()
        required = set(TASK_REQUIRED_CAPABILITIES.get(task, frozenset()))
        if request.requires_streaming:
            required.add("streaming")
        if request.requires_structured_output:
            required.add("structured_output")
        privacy = (
            request.privacy_preference or self._settings.jarvis_llm_privacy_preference or "any"
        ).strip().lower()
        if privacy == "local":
            required.add("local_private")
        return frozenset(required)

    def _eligible(self, request: RouteRequest) -> list[str]:
        required = self._required_caps(request)
        eligible: list[str] = []
        for name in configured_provider_names(self._settings):
            spec = PROVIDER_SPECS.get(name)
            if spec is None:
                continue
            if not required.issubset(spec.capabilities):
                continue
            eligible.append(name)
        return eligible

    def _order(self, candidates: list[str], request: RouteRequest) -> list[str]:
        preferred = (request.preferred_provider or "").strip().lower()
        explicit = preferred if preferred in candidates else ""
        cost_pref = (
            request.cost_preference or self._settings.jarvis_llm_cost_preference or "balanced"
        ).strip().lower()
        lat_pref = (
            request.latency_preference or self._settings.jarvis_llm_latency_preference or "balanced"
        ).strip().lower()

        default = (
            self._settings.jarvis_llm_routing_default or self._settings.jarvis_llm_provider or ""
        ).strip().lower()
        fallback = [
            name
            for name in parse_provider_list(self._settings.jarvis_llm_fallback_providers)
            if name in candidates
        ]

        def sort_key(name: str) -> tuple[int, int, int, str]:
            spec = PROVIDER_SPECS[name]
            cost = spec.cost_tier if cost_pref == "lowest" else 0
            latency = spec.latency_tier if lat_pref == "lowest" else 0
            # Prefer fallback-list order when not optimizing cost/latency.
            try:
                fallback_rank = fallback.index(name)
            except ValueError:
                fallback_rank = 100
            return (cost, latency, fallback_rank, name)

        rest = [name for name in candidates if name != explicit]
        rest_sorted = sorted(rest, key=sort_key)

        if cost_pref != "lowest" and lat_pref != "lowest" and not explicit:
            # Balanced: pin routing default / 10A provider when it still qualifies.
            if default in rest_sorted:
                rest_sorted.remove(default)
                rest_sorted.insert(0, default)

        if explicit:
            return [explicit, *rest_sorted]
        return rest_sorted

    @staticmethod
    def _reason(primary: str, request: RouteRequest, ordered: list[str]) -> str:
        bits = [f"selected {primary}", f"task={request.task or 'chat'}"]
        if request.preferred_provider:
            bits.append("explicit_preference")
        if request.requires_streaming:
            bits.append("streaming")
        if request.requires_structured_output:
            bits.append("structured_output")
        if len(ordered) > 1:
            bits.append("fallbacks=" + ",".join(ordered[1:]))
        return "; ".join(bits)


class RoutingAssistantClient:
    """AssistantLlmClient that executes the selected provider, then fallbacks.

    HTTP stays inside Phase 10A adapters. This wrapper only chooses and
    retries the next configured provider after a typed ``LLMProviderError``.
    ``CancelledError`` is never converted into a fallback.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        router: LlmRouter | None = None,
        task: str = "chat",
        preferred_provider: str | None = None,
        transports: dict[str, Any] | None = None,
        client_builders: dict[str, ClientBuilder] | None = None,
        on_fallback: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._router = router or LlmRouter(settings)
        self._task = task
        self._preferred_provider = preferred_provider
        self._transports = transports or {}
        self._client_builders = client_builders or {}
        self._clients: dict[str, Any] = {}
        #: Optional observer: (failed_provider, next_provider, error_code).
        #: Additive Phase 11 hook — semantics of routing are unchanged.
        self.on_fallback = on_fallback
        self.last_decision: RouteDecision | None = None
        self.enabled = True

    def bind_task(self, task: str) -> RoutingAssistantClient:
        sibling = RoutingAssistantClient(
            self._settings,
            router=self._router,
            task=task,
            preferred_provider=self._preferred_provider,
            transports=self._transports,
            client_builders=self._client_builders,
            on_fallback=self.on_fallback,
        )
        sibling._clients = self._clients
        return sibling

    @property
    def model_name(self) -> str:
        decision = self._router.decide(self._route_request(streaming=False, structured=False))
        return decision.model if decision else ""

    @property
    def provider_name(self) -> str:
        decision = self._router.decide(self._route_request(streaming=False, structured=False))
        return decision.provider if decision else ""

    def _route_request(self, *, streaming: bool, structured: bool) -> RouteRequest:
        return RouteRequest(
            task=self._task,
            requires_streaming=streaming,
            requires_structured_output=structured,
            preferred_provider=self._preferred_provider,
        )

    def _client(self, name: str) -> Any:
        if name in self._clients:
            return self._clients[name]
        if name in self._client_builders:
            client = self._client_builders[name](name)
        else:
            if not is_provider_configured(name, self._settings):
                raise ProviderUnavailableError(f"provider {name} is not configured")
            client = build_provider_client(
                name, self._settings, transport=self._transports.get(name)
            )
        self._clients[name] = client
        return client

    def _chain(self, request: RouteRequest) -> list[str]:
        decision = self._router.decide(request)
        self.last_decision = decision
        if decision is None:
            return []
        return [decision.provider, *decision.fallback_chain]

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        # Intent/narration still use prompt-parsed JSON on every adapter; native
        # json_mode is only a hard filter when the task is structured_json.
        request = self._route_request(
            streaming=False,
            structured=self._task == "structured_json",
        )
        chain = self._chain(request)
        if not chain:
            raise ProviderUnavailableError("no configured provider matches the routing request")
        last_error: LLMProviderError | None = None
        for name in chain:
            try:
                client = self._client(name)
                return await client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    json_mode=json_mode,
                )
            except asyncio.CancelledError:
                raise
            except LLMProviderError as exc:
                last_error = exc
                logger.warning(
                    "LLM provider failed; considering fallback",
                    extra={
                        "provider": name,
                        "error_kind": type(exc).__name__,
                        "error_code": getattr(exc, "code", ""),
                    },
                )
                self._notify_fallback(name, chain, exc)
                continue
        raise ProviderUnavailableError("all routed providers failed") from last_error

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        request = self._route_request(streaming=True, structured=False)
        chain = self._chain(request)
        if not chain:
            raise ProviderUnavailableError("no configured provider matches the routing request")
            yield ""  # pragma: no cover
        last_error: LLMProviderError | None = None
        for name in chain:
            started = False
            try:
                client = self._client(name)
                async for delta in client.stream(
                    system_prompt=system_prompt, user_prompt=user_prompt
                ):
                    started = True
                    if isinstance(delta, str) and delta:
                        yield delta
                return
            except asyncio.CancelledError:
                raise
            except LLMProviderError as exc:
                if started:
                    raise
                last_error = exc
                logger.warning(
                    "LLM stream failed before deltas; considering fallback",
                    extra={
                        "provider": name,
                        "error_kind": type(exc).__name__,
                        "error_code": getattr(exc, "code", ""),
                    },
                )
                self._notify_fallback(name, chain, exc)
                continue
        raise ProviderUnavailableError("all routed providers failed") from last_error

    def _notify_fallback(self, failed: str, chain: list[str], exc: LLMProviderError) -> None:
        """Invoke the optional observer with the NEXT provider (if any)."""
        if self.on_fallback is None:
            return
        try:
            index = chain.index(failed)
        except ValueError:
            return
        nxt = chain[index + 1] if index + 1 < len(chain) else ""
        self.on_fallback(failed, nxt, getattr(exc, "code", "provider_error"))

    async def health(self) -> dict[str, Any]:
        """Probe ONLY the selected primary provider. Timeout-bounded."""
        decision = self._router.decide(self._route_request(streaming=False, structured=False))
        self.last_decision = decision
        if decision is None:
            return {"reachable": False, "model_available": False, "reason": "no_routable_provider"}
        timeout = float(self._settings.jarvis_llm_health_timeout_seconds)
        try:
            client = self._client(decision.provider)
            health = await asyncio.wait_for(client.health(), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - status must never raise
            return {
                "reachable": False,
                "model_available": False,
                "model": decision.model,
            }
        if not isinstance(health, dict):
            return {"reachable": False, "model_available": False, "model": decision.model}
        health.setdefault("model", decision.model)
        return health


def routing_status_fields(
    settings: Settings, *, decision: RouteDecision | None
) -> dict[str, Any]:
    """Safe routing metadata for /api/llm/status — names only, never secrets."""
    caps: list[str] = []
    if decision is not None:
        spec = PROVIDER_SPECS.get(decision.provider)
        if spec is not None:
            caps = sorted(spec.capabilities)
    return {
        "routing_enabled": bool(settings.jarvis_llm_routing_enabled),
        "configured_providers": configured_provider_names(settings),
        "capabilities": caps,
    }


__all__ = [
    "LlmRouter",
    "RouteDecision",
    "RouteRequest",
    "RoutingAssistantClient",
    "bind_assistant_task",
    "routing_status_fields",
]
