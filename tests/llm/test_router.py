"""Phase 10B routing tests. Mocked clients only — no live provider calls."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.llm import create_assistant_llm
from app.llm.base import DisabledAssistantClient, ProviderUnavailableError, safe_status
from app.llm.ollama import OllamaClient
from app.llm.openai import OpenAIClient
from app.llm.router import (
    LlmRouter,
    RouteRequest,
    RoutingAssistantClient,
    bind_assistant_task,
)
from app.main import create_app

SECRET = "sk-SECRET-LEAK-TEST-KEY-9f3a"


def routing_settings(**over: Any) -> Settings:
    base: dict[str, Any] = dict(
        jarvis_assistant_llm_enabled=True,
        jarvis_llm_routing_enabled=True,
        jarvis_llm_provider="ollama",
        jarvis_llm_model="llama3.1",
        jarvis_llm_timeout_seconds=2.0,
        jarvis_llm_health_timeout_seconds=2.0,
        openai_api_key="",
        openrouter_api_key="",
        deepseek_api_key="",
        moonshot_api_key="",
        gemini_api_key="",
        anthropic_api_key="",
        ollama_api_key="",
    )
    base.update(over)
    return Settings(**base)


class ScriptClient:
    enabled = True

    def __init__(
        self,
        name: str,
        *,
        fail: bool = False,
        output: str = "ok",
        chunks: list[str] | None = None,
        fail_after_delta: bool = False,
        block: asyncio.Event | None = None,
    ) -> None:
        self.name = name
        self.model_name = f"{name}-model"
        self.fail = fail
        self.output = output
        self.chunks = chunks if chunks is not None else ["tok"]
        self.fail_after_delta = fail_after_delta
        self.block = block
        self.generate_calls = 0
        self.stream_calls = 0
        self.health_calls = 0

    async def generate(
        self, *, system_prompt: str, user_prompt: str, json_mode: bool = False
    ) -> str:
        self.generate_calls += 1
        if self.block is not None:
            await self.block.wait()
        if self.fail:
            raise ProviderUnavailableError(f"{self.name} unavailable")
        return self.output

    async def stream(self, *, system_prompt: str, user_prompt: str):
        self.stream_calls += 1
        if self.fail:
            raise ProviderUnavailableError(f"{self.name} unavailable")
        for chunk in self.chunks:
            yield chunk
            if self.fail_after_delta:
                raise ProviderUnavailableError(f"{self.name} mid-stream")

    async def health(self) -> dict[str, Any]:
        self.health_calls += 1
        return {"reachable": True, "model_available": True}


def builders(clients: dict[str, ScriptClient]) -> dict[str, Any]:
    return {name: (lambda n, c=client: c) for name, client in clients.items()}


def routed_client(settings: Settings, clients: dict[str, ScriptClient]) -> RoutingAssistantClient:
    return RoutingAssistantClient(
        settings,
        router=LlmRouter(settings),
        client_builders=builders(clients),
    )


# ---------------------------------------------------------------------------
# Selection policy
# ---------------------------------------------------------------------------


class TestRoutingDisabled:
    def test_decide_returns_none(self) -> None:
        settings = routing_settings(jarvis_llm_routing_enabled=False)
        assert LlmRouter(settings).decide() is None

    def test_factory_still_returns_phase10a_client(self) -> None:
        settings = routing_settings(jarvis_llm_routing_enabled=False)
        client = create_assistant_llm(settings)
        assert type(client) is OllamaClient


class TestDefaultProviderSelection:
    def test_balanced_pins_routing_default(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_routing_default="openai",
            openai_api_key=SECRET,
            gemini_api_key="gemini-key",
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
        assert decision is not None
        assert decision.provider == "openai"
        assert "gemini" in decision.fallback_chain or "ollama" in decision.fallback_chain

    def test_factory_returns_routing_client(self) -> None:
        settings = routing_settings(openai_api_key=SECRET, jarvis_llm_provider="openai")
        client = create_assistant_llm(settings)
        assert isinstance(client, RoutingAssistantClient)
        assert client.provider_name == "openai"


class TestExplicitPreference:
    def test_explicit_wins_over_cheaper_default(self) -> None:
        settings = routing_settings(
            jarvis_llm_cost_preference="lowest",
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
            gemini_api_key="gemini-key",
        )
        decision = LlmRouter(settings).decide(
            RouteRequest(task="chat", preferred_provider="openai")
        )
        assert decision is not None
        assert decision.provider == "openai"
        assert "explicit_preference" in decision.reason


class TestUnconfiguredAndUnavailable:
    def test_unconfigured_name_never_selected(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
        )
        decision = LlmRouter(settings).decide(
            RouteRequest(preferred_provider="anthropic")
        )
        assert decision is not None
        assert decision.provider == "openai"
        assert "anthropic" not in (decision.provider, *decision.fallback_chain)

    def test_unknown_preferred_is_ignored(self) -> None:
        settings = routing_settings(openai_api_key=SECRET, jarvis_llm_provider="openai")
        decision = LlmRouter(settings).decide(RouteRequest(preferred_provider="skynet"))
        assert decision is not None
        assert decision.provider == "openai"

    def test_factory_does_not_build_unconfigured_cloud(self) -> None:
        settings = routing_settings(
            jarvis_llm_routing_enabled=False,
            jarvis_llm_provider="openai",
            openai_api_key="",
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)


class TestCapabilityMismatch:
    def test_reasoning_requires_reasoning_family(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
        )
        assert LlmRouter(settings).decide(RouteRequest(task="reasoning")) is None

    def test_reasoning_selects_deepseek_when_configured(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
            deepseek_api_key="ds-key",
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="reasoning"))
        assert decision is not None
        assert decision.provider == "deepseek"


class TestStreamingRequirement:
    def test_streaming_keeps_streaming_capable_providers(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
        )
        decision = LlmRouter(settings).decide(
            RouteRequest(task="chat", requires_streaming=True)
        )
        assert decision is not None
        assert decision.provider == "openai"
        assert "streaming" in decision.reason


class TestStructuredOutputRequirement:
    def test_native_json_excludes_ollama(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        decision = LlmRouter(settings).decide(
            RouteRequest(task="structured_json", requires_structured_output=True)
        )
        assert decision is not None
        assert decision.provider == "openai"
        assert "ollama" not in (decision.provider, *decision.fallback_chain)

    def test_ollama_only_cannot_satisfy_native_json(self) -> None:
        settings = routing_settings(jarvis_llm_provider="ollama")
        assert (
            LlmRouter(settings).decide(
                RouteRequest(task="chat", requires_structured_output=True)
            )
            is None
        )


class TestCostAndLatency:
    def test_cost_lowest_prefers_gemini_over_openai(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            jarvis_llm_cost_preference="lowest",
            openai_api_key=SECRET,
            gemini_api_key="gemini-key",
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
        assert decision is not None
        assert decision.provider == "gemini"

    def test_latency_lowest_prefers_gemini(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            jarvis_llm_latency_preference="lowest",
            openai_api_key=SECRET,
            gemini_api_key="gemini-key",
            anthropic_api_key="ant-key",
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
        assert decision is not None
        assert decision.provider == "gemini"


class TestFallbackOrdering:
    def test_fallback_list_order_in_chain(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai,gemini,deepseek",
            openai_api_key=SECRET,
            gemini_api_key="g",
            deepseek_api_key="d",
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
        assert decision is not None
        assert decision.provider == "ollama"
        assert decision.fallback_chain[:3] == ("openai", "gemini", "deepseek")


class TestProviderFailureFallback:
    async def test_generate_walks_chain(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        ollama = ScriptClient("ollama", fail=True)
        openai = ScriptClient("openai", output="from-openai")
        client = routed_client(settings, {"ollama": ollama, "openai": openai})
        text = await client.generate(system_prompt="s", user_prompt="u")
        assert text == "from-openai"
        assert ollama.generate_calls == 1
        assert openai.generate_calls == 1
        assert ollama.health_calls == 0
        assert openai.health_calls == 0

    async def test_stream_fallback_before_first_delta(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        ollama = ScriptClient("ollama", fail=True)
        openai = ScriptClient("openai", chunks=["a", "b"])
        client = routed_client(settings, {"ollama": ollama, "openai": openai})
        got = [d async for d in client.stream(system_prompt="s", user_prompt="u")]
        assert got == ["a", "b"]
        assert openai.stream_calls == 1

    async def test_stream_does_not_switch_after_deltas(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        ollama = ScriptClient("ollama", chunks=["partial"], fail_after_delta=True)
        openai = ScriptClient("openai", chunks=["other"])
        client = routed_client(settings, {"ollama": ollama, "openai": openai})
        with pytest.raises(ProviderUnavailableError):
            _ = [d async for d in client.stream(system_prompt="s", user_prompt="u")]
        assert openai.stream_calls == 0


class TestAllProvidersFailDeterministic:
    async def test_routing_client_raises_after_exhausted_chain(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        client = routed_client(
            settings,
            {
                "ollama": ScriptClient("ollama", fail=True),
                "openai": ScriptClient("openai", fail=True),
            },
        )
        with pytest.raises(ProviderUnavailableError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "provider_unavailable"
        assert SECRET not in str(excinfo.value)

    async def test_orchestrator_uses_deterministic_narration(self) -> None:
        from tests.llm.test_orchestrator_llm import make_orch

        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
            candidate_redact_pii=True,
        )
        llm = routed_client(
            settings,
            {
                "ollama": ScriptClient("ollama", fail=True),
                "openai": ScriptClient("openai", fail=True),
            },
        )
        orchestrator, session, sent, send = make_orch({}, llm)
        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()
        types = [e["type"] for e in sent]
        assert "error" not in types
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert "job(s)" in assistant["data"]["text"]


class TestNoUnnecessaryHealth:
    def test_decide_does_not_construct_clients(self) -> None:
        settings = routing_settings(openai_api_key=SECRET, jarvis_llm_provider="openai")
        constructed: list[str] = []

        def builder(name: str) -> ScriptClient:
            constructed.append(name)
            return ScriptClient(name)

        router = LlmRouter(settings)
        decision = router.decide(RouteRequest(task="chat"))
        assert decision is not None
        assert constructed == []
        client = RoutingAssistantClient(
            settings, router=router, client_builders={"openai": builder}
        )
        # model_name/property uses decide only
        assert client.model_name == "llama3.1"
        assert constructed == []

    async def test_generate_skips_health(self) -> None:
        settings = routing_settings(openai_api_key=SECRET, jarvis_llm_provider="openai")
        openai = ScriptClient("openai", output="hi")
        client = routed_client(settings, {"openai": openai})
        await client.generate(system_prompt="s", user_prompt="u")
        assert openai.health_calls == 0
        assert openai.generate_calls == 1


class TestSecretsNeverLeak:
    def test_decision_and_status_omit_keys(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
            jarvis_llm_model="gpt-4o-mini",
        )
        decision = LlmRouter(settings).decide()
        assert decision is not None
        blob = json.dumps(
            {
                "provider": decision.provider,
                "model": decision.model,
                "reason": decision.reason,
                "fallback": list(decision.fallback_chain),
                "status": safe_status(
                    True,
                    decision.provider,
                    decision.model,
                    False,
                    routing_enabled=True,
                    configured_providers=["openai"],
                    capabilities=["streaming"],
                ),
            }
        )
        assert SECRET not in blob
        assert "Authorization" not in blob

    def test_http_status_omits_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = routing_settings(
            database_url="sqlite+pysqlite:///:memory:",
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
            jarvis_llm_model="gpt-4o-mini",
        )

        class Fake:
            enabled = True
            provider_name = "openai"
            model_name = "gpt-4o-mini"

            async def health(self) -> dict[str, Any]:
                return {"reachable": True}

        monkeypatch.setattr("app.api.routes.llm.create_assistant_llm", lambda _s: Fake())
        http = TestClient(create_app(settings))
        payload = http.get("/api/llm/status").json()
        blob = json.dumps(payload)
        assert SECRET not in blob
        assert payload["routing_enabled"] is True
        assert payload["provider"] == "openai"
        assert "openai" in payload["configured_providers"]


class TestConcurrencyAndCancellation:
    async def test_concurrent_generate(self) -> None:
        settings = routing_settings(openai_api_key=SECRET, jarvis_llm_provider="openai")
        openai = ScriptClient("openai", output="ok")
        client = routed_client(settings, {"openai": openai})
        results = await asyncio.gather(
            *[client.generate(system_prompt="s", user_prompt=f"u{i}") for i in range(8)]
        )
        assert results == ["ok"] * 8
        assert openai.generate_calls == 8

    async def test_cancel_does_not_start_fallback(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            openai_api_key=SECRET,
        )
        gate = asyncio.Event()
        ollama = ScriptClient("ollama", block=gate)
        openai = ScriptClient("openai", output="fallback")
        client = routed_client(settings, {"ollama": ollama, "openai": openai})
        task = asyncio.create_task(client.generate(system_prompt="s", user_prompt="u"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        gate.set()
        await asyncio.sleep(0.05)
        assert openai.generate_calls == 0


class TestBindAndPrivacy:
    def test_bind_task_is_noop_for_plain_clients(self) -> None:
        plain = ScriptClient("openai")
        assert bind_assistant_task(plain, "intent") is plain

    def test_local_privacy_keeps_only_ollama(self) -> None:
        settings = routing_settings(
            jarvis_llm_privacy_preference="local",
            jarvis_llm_provider="ollama",
            openai_api_key=SECRET,
        )
        decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
        assert decision is not None
        assert decision.provider == "ollama"
        assert decision.fallback_chain == ()

    def test_routing_enabled_with_empty_pool_disables(self) -> None:
        settings = routing_settings(
            jarvis_llm_provider="openai",
            openai_api_key="",
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)


class TestPhase10AFactoryUnchangedWhenRoutingOff:
    def test_openai_factory_type(self) -> None:
        settings = routing_settings(
            jarvis_llm_routing_enabled=False,
            jarvis_llm_provider="openai",
            openai_api_key=SECRET,
        )
        assert type(create_assistant_llm(settings)) is OpenAIClient
