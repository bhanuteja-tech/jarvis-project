"""Orchestrator x LLM integration: refinement, narration, token events.

Uses the same FakeGraph pattern as Phase 9 E2E plus a scripted FakeLLM.
"""

from __future__ import annotations

import json
from typing import Any

from app.config.settings import Settings
from app.jarvis.events import EventType
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore

JOB = {
    "id": "job-1",
    "source": "greenhouse",
    "source_job_id": "1",
    "title": "Python Engineer",
    "company": "TargetCo",
}

UPDATES = [
    {"fetch_sources": {"jobs": [JOB]}},
    {"build_candidate_profile": {"candidate_profile": {"status": "PARSED", "profile": {}}}},
    {
        "match_candidate_to_jobs": {
            "match_results": [
                {"job_index": 0, "score": 90, "tier": "strong",
                 "matched_skills": ["python"], "missing_required": []}
            ]
        }
    },
]


class FakeLLM:
    enabled = True
    model_name = "fake-model"

    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_chunks: list[str] | None = None
        self.fail_generate = False

    async def generate(self, *, system_prompt: str, user_prompt: str,
                       json_mode: bool = False) -> str:
        if self.fail_generate:
            from app.llm.base import ProviderUnavailableError

            raise ProviderUnavailableError("mock outage")
        self.generate_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        return json.dumps({"text": "Polished narration of verified facts."})

    async def stream(self, *, system_prompt: str, user_prompt: str):
        for chunk in (self.stream_chunks or ["Hello ", "world"]):
            yield chunk


def make_orch(settings_overrides: dict[str, Any], llm: Any):
    sent: list[dict[str, Any]] = []

    async def send(envelope: dict[str, Any]) -> None:
        sent.append(envelope)

    settings = Settings(
        jarvis_assistant_llm_enabled=True,
        candidate_redact_pii=True,
        **settings_overrides,
    )
    store = InMemorySessionStore()
    session = store.get_or_create("s-llm")
    orchestrator = JarvisOrchestrator(
        settings,
        session_store=store,
        graph_factory=lambda: _Scripted(UPDATES),
        llm_client=llm,
    )
    return orchestrator, session, sent, send


class _Scripted:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self._updates = updates

    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        for update in self._updates:
            yield update


class TestOrchestratorLlm:
    async def test_disabled_flag_means_no_llm_attribute_use(self) -> None:
        llm = FakeLLM()
        orchestrator, session, sent, send = make_orch({}, llm)
        # Force-disable via settings path: rebuild with flag off.
        orchestrator._llm = None  # noqa: SLF001 - direct deterministic check
        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()
        assert llm.generate_calls == []
        assert not any(e["type"] == "token" for e in sent)
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert "job(s)" in assistant["data"]["text"]  # deterministic narrator

    async def test_narration_overrides_with_llm_text(self) -> None:
        llm = FakeLLM()
        orchestrator, session, sent, send = make_orch({}, llm)

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        assert llm.generate_calls, "narration should call the provider"
        # Facts boundary: prompt carries verified facts JSON only.
        user_prompt = llm.generate_calls[0]["user_prompt"]
        facts = json.loads(user_prompt)["facts"]
        assert facts["top_matches"][0]["title"] == "Python Engineer"
        assert "@example.com" not in user_prompt

        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert assistant["data"]["text"] == "Polished narration of verified facts."
        # snapshot still canonical on the same message
        assert "result_snapshot" in assistant["data"]

    async def test_provider_failure_falls_back_to_deterministic(self) -> None:
        llm = FakeLLM()
        llm.fail_generate = True
        orchestrator, session, sent, send = make_orch({}, llm)

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        types = [e["type"] for e in sent]
        assert "error" not in types  # outage must not become an application error
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert "job(s)" in assistant["data"]["text"]
        assert types[-1] == "completed"

    async def test_streaming_emits_real_token_events_then_final_message(self) -> None:
        llm = FakeLLM()
        orchestrator, session, sent, send = make_orch(
            {"jarvis_llm_streaming": True}, llm
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        tokens = [e for e in sent if e["type"] == EventType.TOKEN]
        assert [t["data"]["text"] for t in tokens] == ["Hello ", "world"]
        seqs = [e["seq"] for e in sent]
        assert seqs == sorted(set(seqs))  # tokens keep monotonic ordering
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert assistant["data"]["text"] == "Hello world"

    async def test_free_text_refined_via_structured_intent(self) -> None:
        llm = FakeLLM()
        captured: dict[str, Any] = {}

        original_generate = llm.generate

        async def spy_generate(**kwargs):
            captured.setdefault("order", []).append(kwargs["user_prompt"])
            return await original_generate(**kwargs)

        llm.generate = spy_generate  # type: ignore[method-assign]

        orchestrator, session, sent, send = make_orch({}, llm)

        await orchestrator.handle_message(
            session,
            {"type": "chat",
             "text": "Can you find backend roles around Berlin that fit me?"},
            send=send,
        )
        await orchestrator.wait_for_run()

        # First LLM call is intent refinement (the raw user message).
        assert captured["order"][0].startswith("Can you find backend")
