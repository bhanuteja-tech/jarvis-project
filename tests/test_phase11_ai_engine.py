"""Phase 11: AI-engine control surface — providers catalog, preferences,
routing visibility events. Mocked transports only; no real provider calls."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.jarvis.events import EventType
from app.llm.preferences import preference_store
from app.main import create_app


def make_app(**settings_overrides):
    from app.main import create_app
    from tests.support import make_settings as base_settings

    settings = base_settings(**{
        "jarvis_assistant_llm_enabled": True,
        "jarvis_llm_provider": "ollama",
        "jarvis_llm_model": "llama3.1:8b",
        "jarvis_llm_routing_enabled": True,
        **settings_overrides,
    })
    return create_app(settings), settings


def client_with(app) -> TestClient:
    return TestClient(app)


class TestProvidersCatalog:
    def test_lists_all_known_providers_with_safe_fields(self) -> None:
        app, _settings = make_app()
        with client_with(app) as c:
            response = c.get("/api/llm/providers")
        assert response.status_code == 200
        rows = response.json()["providers"]
        names = {row["name"] for row in rows}
        assert {
            "ollama", "openai", "openrouter", "deepseek",
            "moonshot", "gemini", "anthropic",
        } <= names
        for row in rows:
            assert set(row) <= {
                "name", "configured", "capabilities", "model",
                "reachable", "model_available", "health_status",
            }
            assert isinstance(row["configured"], bool)
            # Never any credential-ish key anywhere in the payload.
            blob = json.dumps(row).lower()
            assert "api_key" not in blob and "authorization" not in blob
            assert "bearer" not in blob and "token" not in blob

    def test_unconfigured_providers_have_empty_model(self) -> None:
        app, _settings = make_app(
            openai_api_key="", openrouter_api_key="",
            deepseek_api_key="", moonshot_api_key="",
            gemini_api_key="", anthropic_api_key="",
        )
        with client_with(app) as c:
            rows = c.get("/api/llm/providers").json()["providers"]
        by_name = {row["name"]: row for row in rows}
        assert by_name["openai"]["configured"] is False
        assert by_name["openai"]["model"] == ""
        assert by_name["deepseek"]["configured"] is False
        # Ollama needs no credential: configured by default.
        assert by_name["ollama"]["configured"] is True

    def test_active_provider_probe_reports_reachability(self) -> None:
        # Point the active provider at a guaranteed-closed port so the probe
        # is deterministic regardless of whether Ollama runs on this machine.
        app, _settings = make_app(jarvis_llm_base_url="http://127.0.0.1:9")
        with client_with(app) as c:
            rows = c.get("/api/llm/providers").json()["providers"]
        ollama_row = next(r for r in rows if r["name"] == "ollama")
        assert ollama_row["reachable"] is False
        assert ollama_row["health_status"] in {"unreachable", ""}

    def test_status_includes_session_preferences_echo(self) -> None:
        app, settings = make_app(deepseek_api_key="k")
        with client_with(app) as c:
            save = c.post(
                "/api/llm/preferences?session_id=sx",
                json={"routing_enabled": True,
                      "preferred_provider": "deepseek",
                      "fallback_providers": ["ollama"]},
            )
            assert save.status_code == 200, save.text
            status = c.get("/api/llm/status?session_id=sx").json()

        assert status["preferred_provider"] == "deepseek"
        assert status["fallback_providers"] == ["ollama"]
        assert status["session_routing_override"] is True
        _ = settings


class TestPreferenceValidation:
    def _post(self, c, payload, session_id="s1"):
        return c.post(
            f"/api/llm/preferences?session_id={session_id}", json=payload
        )

    def test_unknown_provider_rejected_400(self) -> None:
        app, _s = make_app()
        with client_with(app) as c:
            r = self._post(c, {"preferred_provider": "skynet"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "unknown_provider"

    def test_unconfigured_provider_rejected_400(self) -> None:
        app, _s = make_app(anthropic_api_key="")
        with client_with(app) as c:
            r = self._post(c, {"preferred_provider": "anthropic"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "unconfigured_provider"

    def test_unknown_fallback_rejected(self) -> None:
        app, _s = make_app(gemini_api_key="g")
        with client_with(app) as c:
            r = self._post(c, {"fallback_providers": ["gemini", "nope"]})
        assert r.status_code == 400

    def test_missing_session_rejected(self) -> None:
        app, _s = make_app()
        with client_with(app) as c:
            r = c.post("/api/llm/preferences", json={"routing_enabled": True})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "missing_session"

    def test_valid_save_roundtrip_and_overwrite(self) -> None:
        app, _s = make_app(deepseek_api_key="k", gemini_api_key="g")
        with client_with(app) as c:
            r1 = self._post(c, {"routing_enabled": True,
                                "preferred_provider": "deepseek",
                                "fallback_providers": ["gemini", "ollama"]}, "sess")
            assert r1.status_code == 200
            body = r1.json()
            assert body["preferred_provider"] == "deepseek"
            assert body["fallback_providers"] == ["gemini", "ollama"]

            # preferred dropped from fallback automatically on overwrite
            r2 = self._post(c, {"routing_enabled": False,
                                "preferred_provider": "",
                                "fallback_providers": ["deepseek"]}, "sess")
            assert r2.status_code == 200
            assert r2.json()["fallback_providers"] == ["deepseek"]

    def test_too_many_fallbacks_rejected(self) -> None:
        app, s = make_app(
            deepseek_api_key="d", gemini_api_key="g", anthropic_api_key="a",
            openai_api_key="o", openrouter_api_key="r", moonshot_api_key="m",
        )
        with client_with(app) as c:
            r = self._post(c, {
                "fallback_providers": [
                    "deepseek", "gemini", "anthropic",
                    "openai", "openrouter", "moonshot", "ollama",
                ]
            })
        assert r.status_code == 400

    def test_preferences_never_contain_secrets(self) -> None:
        app, _s = make_app(deepseek_api_key="super-secret-key-123")
        with client_with(app) as c:
            r = self._post(c, {"preferred_provider": "deepseek"})
        assert "super-secret-key-123" not in r.text


# ---------------------------------------------------------------------------
# Routing visibility through the orchestrator (real events, fake clients)
# ---------------------------------------------------------------------------


class ScriptedProviderClient:
    """Fails N times then succeeds — exercises the fallback hook."""

    enabled = True
    model_name = "fake-model"

    def __init__(self, name: str, failures: int, state: dict) -> None:
        self.provider_name = name
        self._failures = failures
        self._state = state

    async def generate(self, *, system_prompt: str, user_prompt: str,
                       json_mode: bool = False) -> str:
        key = self.provider_name
        used = self._state.setdefault("used", {}).get(key, 0)
        self._state["used"][key] = used + 1
        if used < self._failures:
            from app.llm.base import ProviderUnavailableError

            raise ProviderUnavailableError(f"{key} down")
        return json.dumps({"text": f"handled-by-{self.provider_name}"})

    async def stream(self, *, system_prompt: str, user_prompt: str):
        raise NotImplementedError
        yield ""

    async def health(self):
        return {"reachable": True, "model_available": True}


class TestRoutingVisibilityEvents:
    def _orchestrator(self, builders, provider: str = "ollama"):
        from app.jarvis.orchestrator import JarvisOrchestrator
        from app.jarvis.sessions import InMemorySessionStore
        from app.llm.router import RoutingAssistantClient

        sent: list[dict] = []

        async def send(envelope: dict) -> None:
            sent.append(envelope)

        settings = Settings(
            jarvis_assistant_llm_enabled=True,
            jarvis_llm_routing_enabled=True,
            jarvis_llm_provider=provider,
            # generate-path tests: ambient .env must not flip these to stream.
            jarvis_llm_streaming=False,
            candidate_redact_pii=True,
        )
        store = InMemorySessionStore()
        session = store.get_or_create("s-route")
        orchestrator = JarvisOrchestrator(
            settings,
            session_store=store,
            graph_factory=lambda: _NoopGraph(),
            llm_client=RoutingAssistantClient(
                settings,
                client_builders={
                    name: lambda n=name: builders[n](n)
                    for name in builders
                },
            ),
        )
        return orchestrator, session, sent, send

    async def test_selected_event_emitted_before_narration(self) -> None:
        state: dict = {"used": {}}
        builders = {
            "ollama": lambda n: ScriptedProviderClient(n, 0, state),
        }
        orchestrator, session, sent, send = self._orchestrator(builders)

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find jobs"}, send=send
        )
        await orchestrator.wait_for_run()

        selected = [e for e in sent if e["type"] == EventType.LLM_PROVIDER_SELECTED]
        assert selected and selected[0]["data"]["provider"] == "ollama"
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        meta = next(a for a in assistant["data"]["attachments"]
                    if a.get("kind") == "llm_meta")
        assert meta["provider"] == "ollama"
        assert isinstance(meta["duration_ms"], (int, float))
        # Safe metadata only.
        assert "key" not in json.dumps(meta).lower()
        assert "token" not in json.dumps(meta).lower() or "tokens" in json.dumps(meta)

    async def test_fallback_event_on_first_provider_failure(self) -> None:
        state: dict = {"used": {}}
        # Pin deepseek as routing default (jarvis_llm_provider) so it is tried
        # FIRST and fails; ollama then serves the request and the fallback
        # hook must fire.
        import app.llm.catalog as catalog

        original_configured = catalog.is_provider_configured

        def fake_configured(name, settings):
            if name in {"deepseek", "ollama"}:
                return True
            return original_configured(name, settings)

        catalog.is_provider_configured = fake_configured
        try:
            builders = {
                "deepseek": lambda n: ScriptedProviderClient(n, 1, state),
                "ollama": lambda n: ScriptedProviderClient(n, 0, state),
            }
            orchestrator, session, sent, send = self._orchestrator(
                builders, provider="deepseek"
            )
            await orchestrator.handle_message(
                session, {"type": "chat", "text": "find jobs"}, send=send
            )
            await orchestrator.wait_for_run()
        finally:
            catalog.is_provider_configured = original_configured

        fallbacks = [e for e in sent if e["type"] == EventType.LLM_FALLBACK]
        assert fallbacks, "expected a typed llm_fallback event"
        data = fallbacks[0]["data"]
        assert data["from"] == "deepseek"
        assert data["to"] == "ollama"

        assistant = next(e for e in sent if e["type"] == "assistant_message")
        meta = next(a for a in assistant["data"]["attachments"]
                    if a.get("kind") == "llm_meta")
        assert meta["fallbacks"] == [{"from": "deepseek", "to": "ollama",
                                      "code": "provider_unavailable"}]
        assert meta["provider"] == "ollama"

    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        yield {"fetch_sources": {"jobs": []}}


# ---------------------------------------------------------------------------
# Deterministic mode guarantees (Phase 11 must not break them)
# ---------------------------------------------------------------------------


class TestDeterministicStillSafe:
    def test_disabled_status_has_no_routing_leaks(self) -> None:
        app = create_app(Settings(jarvis_assistant_llm_enabled=False))
        with TestClient(app) as c:
            status = c.get("/api/llm/status").json()
            providers = c.get("/api/llm/providers").json()
        assert status["enabled"] is False
        assert status["provider"] == ""
        assert status["routing_enabled"] is False
        # Catalog still lists names (safe), but nothing is reachable-flagged.
        assert all("reachable" not in row or row["reachable"] is not True
                   for row in providers["providers"])

    def test_preference_store_isolated_per_session(self) -> None:
        preference_store.clear_all() if hasattr(preference_store, "clear_all") else None
        app, _s = make_app(deepseek_api_key="k")
        with TestClient(app) as c:
            c.post("/api/llm/preferences?session_id=A",
                   json={"preferred_provider": "deepseek"})
            status_b = c.get("/api/llm/status?session_id=B").json()
        assert status_b["preferred_provider"] == ""

class _NoopGraph:
    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        yield {"fetch_sources": {"jobs": []}}
