"""Phase 10C: production Ollama / ngrok behaviour. MockTransport only."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.llm import create_assistant_llm
from app.llm.base import (
    DisabledAssistantClient,
    LLMConfigurationError,
    LLMProviderError,
    ProviderUnavailableError,
)
from app.llm.ollama import OllamaClient
from app.llm.ollama_endpoint import resolve_ollama_base_url
from app.llm.router import LlmRouter, RoutingAssistantClient
from app.main import create_app
from tests.llm.providers import ollama_chat_response, ollama_tags
from tests.llm.test_orchestrator_llm import make_orch
from tests.llm.test_providers import make_settings
from tests.llm.test_router import ScriptClient, routed_client

TOKEN = "ngrok-secret-TOKEN-never-leak"
REMOTE_HTTPS = "https://secure-example.ngrok.app"


def _client(settings: Settings, handler) -> OllamaClient:
    return OllamaClient(settings, transport=httpx.MockTransport(handler))


class TestLocalhostOllama:
    async def test_loopback_generate(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return ollama_chat_response("local-ok")

        settings = make_settings(jarvis_llm_base_url="http://127.0.0.1:11434")
        text = await _client(settings, handler).generate(
            system_prompt="s", user_prompt="u"
        )
        assert text == "local-ok"
        assert str(seen[0].url).startswith("http://127.0.0.1:11434/")
        assert "authorization" not in seen[0].headers


class TestRemoteHttpsOllama:
    async def test_remote_https_is_used_verbatim(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return ollama_chat_response("remote-ok")

        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS,
            jarvis_ollama_require_https=True,
            ollama_api_key=TOKEN,
        )
        text = await _client(settings, handler).generate(
            system_prompt="s", user_prompt="u"
        )
        assert text == "remote-ok"
        assert str(seen[0].url).startswith(REMOTE_HTTPS + "/api/chat")
        assert seen[0].url.scheme == "https"


class TestTrailingSlashAndAliases:
    def test_trailing_slash_stripped(self) -> None:
        settings = make_settings(jarvis_llm_base_url=REMOTE_HTTPS + "/")
        assert resolve_ollama_base_url(settings) == REMOTE_HTTPS

    def test_ollama_base_url_used_when_generic_empty(self) -> None:
        settings = make_settings(
            jarvis_llm_base_url="",
            ollama_base_url="https://alias.example/",
        )
        assert resolve_ollama_base_url(settings) == "https://alias.example"

    def test_generic_url_wins_over_alias(self) -> None:
        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS,
            ollama_base_url="http://127.0.0.1:11434",
        )
        assert resolve_ollama_base_url(settings) == REMOTE_HTTPS


class TestMissingAndInvalidConfiguration:
    async def test_invalid_url_is_typed_configuration_error(self) -> None:
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return ollama_chat_response("nope")

        settings = make_settings(jarvis_llm_base_url="not-a-url")
        client = _client(settings, handler)
        with pytest.raises(LLMConfigurationError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "configuration_error"
        assert called["n"] == 0
        health = await client.health()
        assert health["status"] == "configuration_error"
        assert health["reachable"] is False

    async def test_disabled_health_is_not_configured(self) -> None:
        client = create_assistant_llm(make_settings(jarvis_assistant_llm_enabled=False))
        assert isinstance(client, DisabledAssistantClient)
        health = await client.health()
        assert health["status"] == "not_configured"


class TestBearerToken:
    async def test_api_key_sent_on_generate_and_health(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.path.endswith("/api/tags"):
                return ollama_tags(["llama3.1"])
            return ollama_chat_response("ok")

        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS, ollama_api_key=TOKEN
        )
        client = _client(settings, handler)
        await client.generate(system_prompt="s", user_prompt="u")
        await client.health()
        assert all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in seen)

    async def test_auth_token_alias_when_api_key_empty(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return ollama_chat_response("ok")

        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS,
            ollama_api_key="",
            ollama_auth_token=TOKEN,
        )
        await _client(settings, handler).generate(system_prompt="s", user_prompt="u")
        assert seen[-1].headers["authorization"] == f"Bearer {TOKEN}"


class TestTokenNeverExposed:
    async def test_errors_and_health_omit_token(self) -> None:
        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS, ollama_api_key=TOKEN
        )
        client = _client(
            settings, lambda r: ollama_chat_response("denied", status_code=401)
        )
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        blob = str(excinfo.value) + json.dumps(await client.health())
        assert TOKEN not in blob
        assert "Authorization" not in blob

    def test_status_endpoint_omits_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = make_settings(
            database_url="sqlite+pysqlite:///:memory:",
            jarvis_llm_base_url=REMOTE_HTTPS,
            ollama_api_key=TOKEN,
        )

        class Fake:
            enabled = True
            provider_name = "ollama"
            model_name = "llama3.1"

            async def health(self) -> dict:
                return {
                    "reachable": True,
                    "model_available": True,
                    "status": "reachable",
                }

        monkeypatch.setattr("app.api.routes.llm.create_assistant_llm", lambda _s: Fake())
        payload = TestClient(create_app(settings)).get("/api/llm/status").json()
        blob = json.dumps(payload)
        assert TOKEN not in blob
        assert "Bearer" not in blob
        assert payload["health_status"] == "reachable"
        assert payload["model_available"] is True


class TestHttpsValidation:
    async def test_http_remote_rejected_when_https_required(self) -> None:
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return ollama_chat_response("nope")

        settings = make_settings(
            jarvis_llm_base_url="http://insecure.example.ngrok.app",
            jarvis_ollama_require_https=True,
        )
        with pytest.raises(LLMConfigurationError):
            await _client(settings, handler).generate(system_prompt="s", user_prompt="u")
        assert called["n"] == 0

    async def test_loopback_http_allowed_when_https_required(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.scheme == "http"
            return ollama_chat_response("dev-ok")

        settings = make_settings(
            jarvis_llm_base_url="http://127.0.0.1:11434",
            jarvis_ollama_require_https=True,
        )
        text = await _client(settings, handler).generate(
            system_prompt="s", user_prompt="u"
        )
        assert text == "dev-ok"

    async def test_https_is_never_downgraded(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return ollama_chat_response("ok")

        settings = make_settings(
            jarvis_llm_base_url="https://secure-example.ngrok.app",
            jarvis_ollama_require_https=False,
        )
        await _client(settings, handler).generate(system_prompt="s", user_prompt="u")
        assert seen[0].url.scheme == "https"


class TestAuthTimeoutConnectionAndModels:
    async def test_authentication_failure_generate_and_health(self) -> None:
        settings = make_settings(jarvis_llm_base_url=REMOTE_HTTPS, ollama_api_key=TOKEN)
        client = _client(
            settings, lambda r: ollama_chat_response("no", status_code=401)
        )
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"
        health = await _client(
            settings, lambda r: ollama_tags([], status_code=401)
        ).health()
        assert health["status"] == "authentication_failure"
        assert health["reachable"] is True
        assert TOKEN not in json.dumps(health)

    async def test_timeout_and_connection_failure(self) -> None:
        settings = make_settings(jarvis_llm_base_url=REMOTE_HTTPS)

        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        def conn_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        with pytest.raises(LLMProviderError) as timed:
            await _client(settings, timeout_handler).generate(
                system_prompt="s", user_prompt="u"
            )
        assert timed.value.code == "timeout"

        with pytest.raises(LLMProviderError) as conn:
            await _client(settings, conn_handler).generate(
                system_prompt="s", user_prompt="u"
            )
        assert conn.value.code == "provider_unavailable"

    async def test_model_available_and_unavailable(self) -> None:
        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS, jarvis_llm_model="llama3.1"
        )
        ok = await _client(settings, lambda r: ollama_tags(["llama3.1:latest"])).health()
        assert ok["reachable"] is True
        assert ok["model_available"] is True
        missing = await _client(settings, lambda r: ollama_tags(["mistral"])).health()
        assert missing["reachable"] is True
        assert missing["model_available"] is False
        assert missing["status"] == "reachable"

    async def test_health_timeout_and_server_unavailable(self) -> None:
        settings = make_settings(
            jarvis_llm_base_url=REMOTE_HTTPS,
            jarvis_llm_health_timeout_seconds=1.0,
        )

        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        health = await _client(settings, timeout_handler).health()
        assert health["status"] == "unreachable"
        assert health["reachable"] is False

        down = await _client(settings, lambda r: httpx.Response(503, json={})).health()
        assert down["status"] == "server_unavailable"
        assert down["reachable"] is False
        assert "error" not in down


class TestRouterAndDeterministicFallback:
    async def test_router_falls_back_when_ollama_fails(self) -> None:
        settings = Settings(
            jarvis_assistant_llm_enabled=True,
            jarvis_llm_routing_enabled=True,
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            jarvis_llm_model="llama3.1",
            jarvis_llm_base_url=REMOTE_HTTPS,
            openai_api_key="openai-test-key",
        )

        def fail(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("tunnel down")

        ollama = OllamaClient(settings, transport=httpx.MockTransport(fail))
        openai = ScriptClient("openai", output="from-openai")
        client = RoutingAssistantClient(
            settings,
            router=LlmRouter(settings),
            client_builders={
                "ollama": lambda _n: ollama,
                "openai": lambda _n: openai,
            },
        )
        text = await client.generate(system_prompt="s", user_prompt="u")
        assert text == "from-openai"
        assert openai.generate_calls == 1

    async def test_all_providers_fail_uses_deterministic_narration(self) -> None:
        settings = Settings(
            jarvis_assistant_llm_enabled=True,
            jarvis_llm_routing_enabled=True,
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            jarvis_llm_model="llama3.1",
            openai_api_key="openai-test-key",
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
        assert "error" not in [e["type"] for e in sent]
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert "job(s)" in assistant["data"]["text"]

    async def test_exhausted_chain_is_typed(self) -> None:
        settings = Settings(
            jarvis_assistant_llm_enabled=True,
            jarvis_llm_routing_enabled=True,
            jarvis_llm_provider="ollama",
            jarvis_llm_fallback_providers="openai",
            jarvis_llm_model="llama3.1",
            openai_api_key="k",
        )
        client = routed_client(
            settings,
            {
                "ollama": ScriptClient("ollama", fail=True),
                "openai": ScriptClient("openai", fail=True),
            },
        )
        with pytest.raises(ProviderUnavailableError):
            await client.generate(system_prompt="s", user_prompt="u")


class TestFrontendHasNoSecrets:
    def test_static_assets_do_not_embed_provider_secrets(self) -> None:
        root = Path(__file__).resolve().parents[2] / "app" / "static"
        forbidden = (
            "OLLAMA_API_KEY",
            "OLLAMA_AUTH_TOKEN",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "get_secret_value",
            "Authorization",
        )
        scanned = 0
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".js", ".html", ".css"}:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                assert needle not in text, f"{needle} found in {path}"
        assert scanned > 0
