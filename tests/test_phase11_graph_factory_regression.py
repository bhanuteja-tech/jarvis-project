"""Regression: real (non-injected) graph factory + visible guarded failures.

Root cause these tests pin: the constructor stored the staticmethod itself
(expecting ``settings``) where ``_run_discovery`` calls it with zero args, so
every REAL run crashed silently inside the spawned task — client saw
agent_thinking then eternal silence. The guarded wrapper also only logged,
emitting nothing.
"""

from __future__ import annotations

from app.config.settings import Settings
from app.jarvis.orchestrator import EventEmitter, JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore


def make_real_factory_orchestrator(**overrides):
    """Construct WITHOUT graph_factory injection — the production path."""
    sent: list[dict] = []

    async def send(envelope: dict) -> None:
        sent.append(envelope)

    settings = Settings(
        jarvis_assistant_llm_enabled=False,  # deterministic; no provider I/O
        **overrides,
    )
    store = InMemorySessionStore()
    session = store.get_or_create("s-real")
    orchestrator = JarvisOrchestrator(settings, session_store=store)
    return orchestrator, store, sent, send, session


class TestDefaultGraphFactory:
    def test_constructor_binds_zero_arg_callable(self) -> None:
        orchestrator, _store, _sent, _send, _session = make_real_factory_orchestrator()
        # The bug: this attribute WAS the static function needing `settings`.
        assert callable(orchestrator._graph_factory)
        try:
            graph = orchestrator._graph_factory()
        except TypeError as exc:  # pragma: no cover - regression guard
            raise AssertionError(
                "default graph factory must be callable with zero args"
            ) from exc
        assert hasattr(graph, "astream")

    async def test_real_run_emits_pipeline_events(self) -> None:
        """End-to-end with the REAL compiled workflow and a stub adapter."""
        from app.graph.workflow import build_workflow

        class StubAdapter:
            source = "greenhouse"

            def __init__(self, jobs: tuple) -> None:
                self._jobs = jobs

            async def fetch_jobs(self, preferences):
                from app.models.job import Job
                from app.sources.base import FetchResult

                job = Job(
                    source="greenhouse",
                    source_job_id="1",
                    title="Python Engineer",
                    company="TargetCo",
                )
                return FetchResult(jobs=(job,))

        job = {
            "source": "greenhouse",
            "source_job_id": "1",
            "title": "Python Engineer",
            "company": "TargetCo",
        }
        orchestrator, _store, sent, send, session = make_real_factory_orchestrator()
        orchestrator._graph_factory = lambda: build_workflow([StubAdapter((job,))])

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        types = [e["type"] for e in sent]
        assert types[0] == "agent_started"
        assert "workflow_node_completed" in types
        assert types[-1] == "completed"


class TestGuardedFailureVisibility:
    async def test_spawn_crash_emits_typed_error_and_completed(self) -> None:
        orchestrator, _store, sent, send, _session = make_real_factory_orchestrator()
        emitter = EventEmitter(send)

        async def exploding() -> None:
            raise TypeError("boom before workflow")

        orchestrator._spawn_run(emitter, "run-x", exploding)
        await orchestrator.wait_for_run()

        types = [e["type"] for e in sent]
        assert "error" in types
        err = next(e for e in sent if e["type"] == "error")
        assert err["data"]["code"] == "run_failed"
        assert "TypeError" in err["data"]["message"]
        assert types[-1] == "completed"  # run terminates for the client
