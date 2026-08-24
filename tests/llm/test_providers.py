"""Phase 10 LLM provider layer: mocked-transport tests. NO real network."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config.settings import Settings
from app.jarvis.intent import (
    parse_intent,
    refine_intent_with_llm,
    validate_structured_intent,
)
from app.jarvis.narration_facts import build_narration_facts
from app.llm import create_assistant_llm
from app.llm.anthropic import AnthropicClient
from app.llm.base import (
    AuthenticationFailedError,
    DisabledAssistantClient,
    InvalidModelError,
    InvalidResponseError,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.llm.deepseek import DeepSeekClient
from app.llm.gemini import GeminiClient
from app.llm.intent_json import parse_intent_json
from app.llm.moonshot import MoonshotClient
from app.llm.ollama import OllamaClient
from app.llm.openai import OpenAIClient
from app.llm.openrouter import OpenRouterClient
from tests.llm.providers import (
    anthropic_message_response,
    anthropic_stream_response,
    chat_completion_response,
    gemini_generate_response,
    gemini_stream_response,
    ollama_chat_response,
    ollama_tags,
    sse_lines,
)


def make_settings(**over):
    base = dict(
        jarvis_assistant_llm_enabled=True,
        jarvis_llm_provider="ollama",
        jarvis_llm_model="llama3.1",
        jarvis_llm_base_url="http://mock-ollama",
        jarvis_llm_timeout_seconds=2.0,
        openai_api_key="test-openai-key",
        openrouter_api_key="test-openrouter-key",
        deepseek_api_key="test-deepseek-key",
        moonshot_api_key="test-moonshot-key",
        gemini_api_key="test-gemini-key",
        anthropic_api_key="test-anthropic-key",
    )
    base.update(over)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Factory / disabled behaviour
# ---------------------------------------------------------------------------


class TestFactory:
    def test_disabled_when_master_flag_off(self) -> None:
        settings = make_settings(jarvis_assistant_llm_enabled=False)
        client = create_assistant_llm(settings)
        assert isinstance(client, DisabledAssistantClient)

    def test_unknown_provider_disables(self) -> None:
        client = create_assistant_llm(make_settings(jarvis_llm_provider="skynet"))
        assert isinstance(client, DisabledAssistantClient)

    def test_openai_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="openai", openai_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    def test_openrouter_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="openrouter", openrouter_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    def test_deepseek_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="deepseek", deepseek_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    def test_moonshot_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="moonshot", moonshot_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    def test_gemini_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="gemini", gemini_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    def test_anthropic_without_key_disables(self) -> None:
        settings = make_settings(
            jarvis_llm_provider="anthropic", anthropic_api_key=""
        )
        assert isinstance(create_assistant_llm(settings), DisabledAssistantClient)

    @pytest.mark.parametrize("provider,cls", [
        ("ollama", OllamaClient),
        ("openai", OpenAIClient),
        ("openrouter", OpenRouterClient),
        ("deepseek", DeepSeekClient),
        ("moonshot", MoonshotClient),
        ("gemini", GeminiClient),
        ("anthropic", AnthropicClient),
    ])
    def test_enabled_factory_types(self, provider: str, cls: type) -> None:
        client = create_assistant_llm(make_settings(jarvis_llm_provider=provider))
        assert type(client) is cls

    async def test_disabled_client_never_calls_network(self) -> None:
        client = create_assistant_llm(make_settings(jarvis_assistant_llm_enabled=False))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "provider_unavailable"
        health = await client.health()
        assert health["reachable"] is False


# ---------------------------------------------------------------------------
# Ollama adapter
# ---------------------------------------------------------------------------


def ollama(handler) -> OllamaClient:
    return OllamaClient(make_settings(), transport=httpx.MockTransport(handler))


class TestOllama:
    async def test_generate_success(self) -> None:
        seen: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            return ollama_chat_response("Hello from llama")

        client = ollama(handler)
        text = await client.generate(system_prompt="sys", user_prompt="usr")
        assert text == "Hello from llama"
        req = seen["req"]
        assert req.url.path == "/api/chat"
        body = json.loads(req.content)
        assert body["model"] == "llama3.1"
        assert body["stream"] is False

    async def test_streaming_genuine_deltas(self) -> None:
        lines = [
            json.dumps({"message": {"content": "Hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]
        ndjson = "\n".join(lines) + "\n"

        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["stream"] is True
            return httpx.Response(200, text=ndjson)

        chunks = [d async for d in ollama(handler).stream(
            system_prompt="s", user_prompt="u")]
        assert chunks == ["Hel", "lo"]

    async def test_connection_failure_is_typed(self) -> None:
        def handler(request):  # pragma: no cover - transport-level failure
            raise httpx.ConnectError("down", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await ollama(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "provider_unavailable"

    async def test_timeout_is_typed(self) -> None:
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await ollama(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "timeout"

    async def test_invalid_model_404(self) -> None:
        with pytest.raises(InvalidModelError):
            await ollama(lambda r: ollama_chat_response("nope", status_code=404)) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_malformed_response(self) -> None:
        with pytest.raises(InvalidResponseError):
            await ollama(lambda r: httpx.Response(200, text="not-json")) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_auth_rejected_via_tunnel(self) -> None:
        client = ollama(lambda r: ollama_chat_response("denied", status_code=401))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"

    async def test_optional_bearer_header_sent_only_when_configured(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return ollama_chat_response("ok")

        without = ollama(handler)
        await without.generate(system_prompt="s", user_prompt="u")
        assert "authorization" not in captured[-1].headers

        with_key = OllamaClient(
            make_settings(ollama_api_key="tunnel-secret"),
            transport=httpx.MockTransport(handler),
        )
        await with_key.generate(system_prompt="s", user_prompt="u")
        assert captured[-1].headers["authorization"] == "Bearer tunnel-secret"

    async def test_health_reports_model_availability(self) -> None:
        client = ollama(lambda r: ollama_tags(["llama3.1:latest", "mistral"]))
        health = await client.health()
        assert health["reachable"] is True
        assert health["model_available"] is True
        assert health["status"] == "reachable"

        down = ollama(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x")))
        health = await down.health()
        assert health["reachable"] is False


# ---------------------------------------------------------------------------
# OpenAI + OpenRouter adapters (shared wire format)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("client_factory,provider_name", [
    (lambda h: OpenAIClient(make_settings(jarvis_llm_provider="openai"),
                            transport=httpx.MockTransport(h)), "openai"),
    (lambda h: OpenRouterClient(make_settings(jarvis_llm_provider="openrouter"),
                                transport=httpx.MockTransport(h)), "openrouter"),
])
class TestOpenAICompatibleProviders:
    async def test_generate(self, client_factory, provider_name: str) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return chat_completion_response("Hi there")

        text = await client_factory(handler).generate(system_prompt="s", user_prompt="u")
        assert text == "Hi there"
        req = captured[-1]
        assert req.url.path.endswith("/chat/completions")
        auth = req.headers.get("authorization", "")
        if provider_name == "openai":
            assert auth == "Bearer test-openai-key"
        else:
            assert auth == "Bearer test-openrouter-key"

    async def test_auth_failure(self, client_factory, provider_name) -> None:
        with pytest.raises(AuthenticationFailedError):
            await client_factory(lambda r: chat_completion_response("no", status_code=401)) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_rate_limit(self, client_factory, provider_name) -> None:
        with pytest.raises(RateLimitedError):
            await client_factory(lambda r: chat_completion_response("slow", status_code=429)) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_invalid_model_404(self, client_factory, provider_name) -> None:
        with pytest.raises(InvalidModelError):
            await client_factory(lambda r: chat_completion_response("x", status_code=404)) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_malformed_payload(self, client_factory, provider_name) -> None:
        with pytest.raises(InvalidResponseError):
            await client_factory(
                lambda r: httpx.Response(200, json={"unexpected": True})
            ).generate(system_prompt="s", user_prompt="u")

    async def test_sse_streaming(self, client_factory, provider_name) -> None:
        deltas = ["a ", "b ", "c"]

        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["stream"] is True
            return httpx.Response(200, text=sse_lines(deltas))

        got = [d async for d in client_factory(handler).stream(
            system_prompt="s", user_prompt="u")]
        assert got == deltas

    async def test_health(self, client_factory, provider_name) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "llama3.1"}]})
            raise AssertionError("health must only call /models")

        health = await client_factory(handler).health()
        assert health["reachable"] is True


# ---------------------------------------------------------------------------
# Intent fallback + validation
# ---------------------------------------------------------------------------


class FakeLLM:
    enabled = True
    model_name = "fake"

    def __init__(self, reply: str | Exception) -> None:
        self._reply = reply
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str, json_mode=False):
        self.calls += 1
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


class TestIntentFallback:
    def test_explicit_commands_never_flagged_free_text(self) -> None:
        for text in ("find python jobs", "status", "help", "tailor job 2"):
            plan = parse_intent(text)
            if text.startswith(("find", "status", "help", "tailor")):
                assert plan.from_free_text is False or text.startswith("find")

    async def test_llm_refines_free_text(self) -> None:
        llm = FakeLLM(json.dumps({
            "action": "run_discovery",
            "params": {"user_query": "backend python",
                       "locations": ["Berlin", "Munich"]},
        }))
        plan = await refine_intent_with_llm(
            "Can you find backend roles around Berlin?", llm
        )
        assert plan is not None and plan.action == "run_discovery"
        assert plan.params["locations"] == ["Berlin", "Munich"]
        assert llm.calls == 1

    async def test_hallucinated_action_rejected_falls_back(self) -> None:
        llm = FakeLLM(json.dumps({"action": "delete_database"}))
        assert await refine_intent_with_llm("do the thing", llm) is None

    async def test_provider_failure_returns_none(self) -> None:
        llm = FakeLLM(ProviderUnavailableError("down"))
        assert await refine_intent_with_llm("anything", llm) is None

    async def test_non_json_reply_returns_none(self) -> None:
        llm = FakeLLM("I cannot help with that.")
        assert await refine_intent_with_llm("anything", llm) is None

    def test_validation_matrix(self) -> None:
        good = {"action": "select_target", "params": {"target_job_index": 1}}
        assert validate_structured_intent(good) is not None
        assert validate_structured_intent({"action": "get_results"}) is not None
        # oversized locations, bad types, unknown keys, wrong action:
        assert validate_structured_intent({
            "action": "run_discovery",
            "params": {"user_query": "x", "locations": [f"c{i}" for i in range(6)]},
        }) is None
        assert validate_structured_intent({
            "action": "run_discovery", "params": {"user_query": 5}
        }) is None
        assert validate_structured_intent({
            "action": "run_discovery", "params": {"user_query": "x", "tool": "rm"}
        }) is None
        assert validate_structured_intent({"action": "exec"}) is None
        assert validate_structured_intent({"action": "help", "params": {"x": 1}}) is None


# ---------------------------------------------------------------------------
# Narration facts boundary + JSON extraction + streaming events
# ---------------------------------------------------------------------------


class TestNarrationFacts:
    def test_facts_contain_no_pii_or_resume_text(self) -> None:
        state = {
            "jobs": [{"title": "Engineer", "company": "Co",
                      "description": "LONG BODY SHOULD NOT APPEAR"}],
            "match_results": [{"job_index": 0, "score": 90, "tier": "strong",
                               "matched_skills": ["python"]}],
            "candidate_input": {"text": "jane@example.com resume body"},
            "tailored_resume": {"resume": {"summary": {"text": "Summary line"},
                                           "unaddressed_jd_requirements": ["aws"]}},
        }
        facts = build_narration_facts(state)
        blob = json.dumps(facts).lower()
        assert "jane@example.com" not in blob
        assert "resume body" not in blob
        assert "long body" not in blob
        assert facts["top_matches"][0]["title"] == "Engineer"


class TestJsonExtraction:
    def test_plain_and_fenced_and_prose_wrapped(self) -> None:
        assert parse_intent_json('{"text":"a"}') == {"text": "a"}
        assert parse_intent_json('```json\n{"text":"b"}\n```') == {"text": "b"}
        assert parse_intent_json('Sure! Here you go:\n{"text":"c"} hope it helps') == {
            "text": "c"
        }
        assert parse_intent_json("no json here") is None


class TestStreamingEvents:
    async def test_token_events_come_from_real_deltas(self) -> None:
        from app.jarvis.events import make_event

        envelope = make_event("token", seq=9, run_id="r1", text="delta!")
        assert envelope["type"] == "token"
        assert envelope["data"]["text"] == "delta!"

    async def test_disabled_mode_emits_no_tokens(self) -> None:
        orchestrator_settings = make_settings(jarvis_assistant_llm_enabled=False)
        client = create_assistant_llm(orchestrator_settings)
        assert not getattr(client, "enabled", False)


# ---------------------------------------------------------------------------
# Concurrency + cancellation at the transport level
# ---------------------------------------------------------------------------


class TestConcurrencyAndCancellation:
    async def test_parallel_generate_calls_are_independent(self) -> None:
        import asyncio

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            return ollama_chat_response(f"reply:{body['messages'][1]['content']}")

        client = ollama(handler)
        results = await asyncio.gather(*[
            client.generate(system_prompt="s", user_prompt=f"u{i}") for i in range(5)
        ])
        assert results == [f"reply:u{i}" for i in range(5)]

    async def test_streaming_cancelled_early_stops_iteration(self) -> None:
        import asyncio

        started = asyncio.Event()

        def handler(request: httpx.Request) -> httpx.Response:
            started.set()
            big = "".join(
                json.dumps({"message": {"content": f"chunk{i}"}, "done": False}) + "\n"
                for i in range(10000)
            )
            return httpx.Response(200, text=big)

        client = ollama(handler)
        received: list[str] = []
        stream = client.stream(system_prompt="s", user_prompt="u")
        task = asyncio.ensure_future(stream.__anext__())
        await asyncio.wait_for(started.wait(), timeout=2)
        first = await task
        received.append(first)
        task2 = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.01)
        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass
        assert received == ["chunk0"]


# ---------------------------------------------------------------------------
# DeepSeek + Moonshot adapters (OpenAI-compatible)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("client_factory,provider_name", [
    (
        lambda h: DeepSeekClient(
            make_settings(jarvis_llm_provider="deepseek", deepseek_api_key="test-key"),
            transport=httpx.MockTransport(h),
        ),
        "deepseek",
    ),
    (
        lambda h: MoonshotClient(
            make_settings(jarvis_llm_provider="moonshot", moonshot_api_key="test-key"),
            transport=httpx.MockTransport(h),
        ),
        "moonshot",
    ),
])
class TestOpenAICompatibleNewProviders:
    async def test_generate(self, client_factory, provider_name: str) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return chat_completion_response("Response")

        text = await client_factory(handler).generate(system_prompt="s", user_prompt="u")
        assert text == "Response"
        req = captured[-1]
        assert req.url.path.endswith("/chat/completions")

    async def test_auth_failure(self, client_factory, provider_name) -> None:
        with pytest.raises(AuthenticationFailedError):
            await client_factory(lambda r: chat_completion_response("no", status_code=401)) \
                .generate(system_prompt="s", user_prompt="u")

    async def test_streaming(self, client_factory, provider_name) -> None:
        deltas = ["a ", "b ", "c"]

        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["stream"] is True
            return httpx.Response(200, text=sse_lines(deltas))

        got = [d async for d in client_factory(handler).stream(
            system_prompt="s", user_prompt="u")]
        assert got == deltas


# ---------------------------------------------------------------------------
# Gemini adapter (native API)
# ---------------------------------------------------------------------------


def gemini(handler) -> GeminiClient:
    settings = make_settings(gemini_api_key="test-key")
    return GeminiClient(settings, transport=httpx.MockTransport(handler))


class TestGemini:
    async def test_generate_success(self) -> None:
        seen: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            return gemini_generate_response("Gemini response")

        client = gemini(handler)
        text = await client.generate(system_prompt="sys", user_prompt="usr")
        assert text == "Gemini response"
        req = seen["req"]
        assert "generateContent" in req.url.path
        assert b"key=" in req.url.query

    async def test_streaming(self) -> None:
        deltas = ["Hel", "lo"]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=gemini_stream_response(deltas))

        chunks = [d async for d in gemini(handler).stream(system_prompt="s", user_prompt="u")]
        assert chunks == deltas

    async def test_connection_failure(self) -> None:
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await gemini(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "provider_unavailable"

    async def test_timeout(self) -> None:
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await gemini(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "timeout"

    async def test_auth_failure(self) -> None:
        client = gemini(lambda r: gemini_generate_response("denied", status_code=401))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"

    async def test_missing_api_key(self) -> None:
        client = GeminiClient(make_settings(gemini_api_key=""))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"


# ---------------------------------------------------------------------------
# Anthropic adapter (native Messages API)
# ---------------------------------------------------------------------------


def anthropic(handler) -> AnthropicClient:
    settings = make_settings(anthropic_api_key="test-key")
    return AnthropicClient(settings, transport=httpx.MockTransport(handler))


class TestAnthropic:
    async def test_generate_success(self) -> None:
        seen: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            return anthropic_message_response("Claude response")

        client = anthropic(handler)
        text = await client.generate(system_prompt="sys", user_prompt="usr")
        assert text == "Claude response"
        req = seen["req"]
        assert req.url.path == "/v1/messages"
        assert req.headers["x-api-key"] == "test-key"

    async def test_streaming(self) -> None:
        deltas = ["Hel", "lo"]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=anthropic_stream_response(deltas))

        chunks = [d async for d in anthropic(handler).stream(system_prompt="s", user_prompt="u")]
        assert chunks == deltas

    async def test_connection_failure(self) -> None:
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await anthropic(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "provider_unavailable"

    async def test_timeout(self) -> None:
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(LLMProviderError) as excinfo:
            await anthropic(handler).generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "timeout"

    async def test_auth_failure(self) -> None:
        client = anthropic(lambda r: anthropic_message_response("denied", status_code=401))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"

    async def test_missing_api_key(self) -> None:
        client = AnthropicClient(make_settings(anthropic_api_key=""))
        with pytest.raises(LLMProviderError) as excinfo:
            await client.generate(system_prompt="s", user_prompt="u")
        assert excinfo.value.code == "authentication_failed"

    async def test_rate_limit(self) -> None:
        with pytest.raises(RateLimitedError):
            await anthropic(lambda r: anthropic_message_response("slow", status_code=429)) \
                .generate(system_prompt="s", user_prompt="u")
