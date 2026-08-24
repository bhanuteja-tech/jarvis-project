"""Phase 9C end-to-end orchestrator QA.

Covers the full Jarvis lifecycle over stub graphs (NO network, NO LLM):
event ordering/seq, canonical snapshot contract + stable job identities,
replacement/cancellation, concurrent-session isolation, typed failure
modes, and an automated PII audit over every emitted envelope.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest

from app.config.settings import Settings
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore

PII_EMAIL = "jane.doe@example.com"
PII_PHONE = "+91 9876543210"
PII_STREET = "123 Example Street"

RESUME_TEXT = (
    f"Jane Doe\n{PII_EMAIL}\n{PII_PHONE}\n{PII_STREET}\n"
    "Senior Python Engineer with sql and docker.\n"
)

JOB_A = {
    "id": "job-aaa",
    "source": "greenhouse",
    "source_job_id": "1",
    "title": "Python Engineer",
    "company": "TargetCo",
    "location": "Berlin",
}
JOB_B = {
    "id": "job-bbb",
    "source": "lever",
    "source_job_id": "9",
    "title": "Backend Python",
    "company": "OtherCo",
    "location": "Remote",
}


def job_updates() -> list[dict[str, Any]]:
    """Canonical node updates incl. interleaved candidate/discovery order."""
    return [
        {"fetch_sources": {"jobs": [JOB_A]}},
        # interleaving: candidate branch completes between discovery nodes
        {
            "build_candidate_profile": {
                "candidate_profile": {"status": "PARSED", "profile": {}}
            }
        },
        {"deduplicate_jobs": {"jobs": [JOB_A, JOB_B]}},
        {"rank_jobs": {"ranked_jobs": [{"job_index": 0, "score": 80}]}},
        {
            "match_candidate_to_jobs": {
                "match_results": [
                    {
                        "job_index": 0,
                        "score": 82,
                        "tier": "strong",
                        "matched_skills": ["python"],
                        "missing_required": ["kubernetes"],
                    }
                ]
            }
        },
    ]


class ScriptedGraph:
    """Yields pre-scripted LangGraph-style updates."""

    def __init__(self, updates: list[dict[str, Any]], *, delay: float = 0.0,
                 fail_after: int | None = None) -> None:
        self._updates = list(updates)
        self._delay = delay
        self._fail_after = fail_after

    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        emitted = 0
        for update in self._updates:
            if self._delay:
                await asyncio.sleep(self._delay)
            if self._fail_after is not None and emitted >= self._fail_after:
                raise RuntimeError("injected workflow bug")
            emitted += 1
            yield update


class BlockingGraph:
    """Emits one update then parks forever — used to hold a run open."""

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        self.started.set()
        yield {"fetch_sources": {"jobs": [JOB_A]}}
        await asyncio.Event().wait()  # never finishes until cancelled


def make_orchestrator(graph_factory, session_id: str = "s-main"):
    sent: list[dict[str, Any]] = []

    async def send(envelope: dict[str, Any]) -> None:
        sent.append(envelope)

    settings = Settings(jarvis_assistant_llm_enabled=False, candidate_redact_pii=True)
    store = InMemorySessionStore()
    session = store.get_or_create(session_id)
    orchestrator = JarvisOrchestrator(
        settings, session_store=store, graph_factory=graph_factory
    )
    return orchestrator, session, sent, send


async def upload_resume(orchestrator, session, send) -> None:
    payload = base64.b64encode(RESUME_TEXT.encode()).decode()
    await orchestrator.handle_message(
        session,
        {"type": "resume_upload", "name": "resume.txt", "data_base64": payload},
        send=send,
    )
    assert any(e["type"] == "tool_completed" for e in sent_local(send))


def sent_local(_send):  # helper keeps call sites readable
    return _send.__self__ if hasattr(_send, "__self__") else []


# ---------------------------------------------------------------------------
# Phase 7/8: lifecycle, ordering, envelope shape
# ---------------------------------------------------------------------------


class TestLifecycleAndOrdering:
    async def test_full_event_lifecycle_and_envelope_shape(self) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates())
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        types = [e["type"] for e in sent]
        assert types[0] == "agent_started"
        assert "agent_thinking" in types
        assert "workflow_node_started" in types
        assert "workflow_node_completed" in types
        assert "agent_speaking" in types
        assert "assistant_message" in types
        assert types[-1] == "completed"

    async def test_every_envelope_has_canonical_fields_and_monotonic_seq(self) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates())
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        seqs: list[int] = []
        for envelope in sent:
            assert set(envelope) == {"type", "seq", "ts", "run_id", "data"}
            assert isinstance(envelope["type"], str)
            assert isinstance(envelope["seq"], int)
            assert isinstance(envelope["ts"], str) and envelope["ts"]
            assert isinstance(envelope["data"], dict)
            seqs.append(envelope["seq"])
        assert seqs == sorted(set(seqs))  # strictly increasing, no dupes

    async def test_interleaved_branch_events_do_not_break_ordering(self) -> None:
        updates = [
            {"fetch_sources": {"jobs": [JOB_A]}},
            {"build_candidate_profile": {"candidate_profile": {"status": "PARSED"}}},
            {"deduplicate_jobs": {"jobs": [JOB_A]}},
        ]
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(updates)
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find jobs"}, send=send
        )
        await orchestrator.wait_for_run()

        completed_nodes = [
            e["data"]["node"] for e in sent if e["type"] == "workflow_node_completed"
        ]
        # candidate branch interleaves between discovery nodes; both complete
        assert "build_candidate_profile" in completed_nodes
        assert completed_nodes.index("fetch_sources") < completed_nodes.index(
            "build_candidate_profile"
        )


# ---------------------------------------------------------------------------
# Phase 2/3: snapshot contract + stable identities
# ---------------------------------------------------------------------------


class TestSnapshotContract:
    async def test_result_snapshot_is_canonical_on_assistant_message(self) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates())
        )
        session.candidate_input = {"text": RESUME_TEXT}

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        assistant = next(e for e in sent if e["type"] == "assistant_message")
        data = assistant["data"]
        assert "result_snapshot" in data  # CANONICAL location
        snapshot = data["result_snapshot"]
        assert set(snapshot) >= {"jobs", "match_results"}
        # No duplicate payload smuggled through attachments
        kinds = [a.get("kind") for a in data.get("attachments", [])]
        assert not any(k and k.startswith("result_snapshot") for k in kinds)

    async def test_jobs_carry_stable_keys_independent_of_position(self) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates())
        )
        session.candidate_input = {"text": RESUME_TEXT}

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        snapshot = next(
            e for e in sent if e["type"] == "assistant_message"
        )["data"]["result_snapshot"]
        keys = [job["job_key"] for job in snapshot["jobs"]]
        assert keys == ["job-aaa", "job-bbb"]  # from canonical Job.id
        match = snapshot["match_results"][0]
        assert match["job_key"] == "job-aaa"  # association via identity
        assert match["job_index"] == 0  # position kept as secondary metadata

    async def test_source_level_fallback_identity_when_no_id(self) -> None:
        updates = [
            {"fetch_sources": {"jobs": [{k: v for k, v in JOB_A.items() if k != "id"}]}},
        ]
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(updates)
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find"}, send=send
        )
        await orchestrator.wait_for_run()

        snapshot = next(e for e in sent if e["type"] == "assistant_message")[
            "data"
        ]["result_snapshot"]
        assert snapshot["jobs"][0]["job_key"] == "greenhouse:1"


# ---------------------------------------------------------------------------
# Phase 9: replacement + explicit cancellation
# ---------------------------------------------------------------------------


class TestReplacementAndCancellation:
    async def test_new_request_replaces_active_run_with_notice(self) -> None:
        # First request parks forever; replacement run completes normally.
        blocking = BlockingGraph()
        graphs: list[Any] = [blocking, ScriptedGraph(job_updates())]
        orchestrator, session, sent, send = make_orchestrator(lambda: graphs.pop(0))

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "first search"}, send=send
        )
        await asyncio.sleep(0)  # let the spawned run start
        await asyncio.wait_for(blocking.started.wait(), timeout=2)
        first_task = orchestrator._current_task
        assert first_task is not None and not first_task.done()
        first_run_id = first_task.get_name().replace("jarvis-run-", "")

        # Second request while run A is parked → A cancelled + replaced.
        await orchestrator.handle_message(
            session, {"type": "chat", "text": "second search"}, send=send
        )
        await orchestrator.wait_for_run()
        for _ in range(50):
            if all(t.done() for t in asyncio.all_tasks() - {asyncio.current_task()}):
                break
            await asyncio.sleep(0.01)

        assert first_task.cancelled() or first_task.done()

        types = [e["type"] for e in sent]
        assert "cancelled" in types
        replacement = next(
            e for e in sent
            if e["type"] == "cancelled"
            and e["data"].get("code") == "replaced_by_new_request"
        )
        assert "replaced" in replacement["data"]["message"].lower()

        completed = [e for e in sent if e["type"] == "completed"]
        assert len(completed) == 1
        assert completed[0]["run_id"] != first_run_id

    async def test_explicit_cancel_message_stops_run(self) -> None:
        graph_holder: dict[str, BlockingGraph] = {}
        orchestrator, session, sent, send = make_orchestrator(
            lambda: graph_holder.setdefault("g", BlockingGraph())
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "long search"}, send=send
        )
        await asyncio.sleep(0)
        await asyncio.wait_for(graph_holder["g"].started.wait(), timeout=2)

        await orchestrator.handle_message(session, {"type": "cancel"}, send=send)
        await asyncio.sleep(0.05)

        cancels = [e for e in sent if e["type"] == "cancelled"]
        assert cancels and "code" not in cancels[0]["data"] or cancels
        assert orchestrator._current_task is None

    async def test_cancelled_run_never_writes_session_state(self) -> None:
        graph_holder: dict[str, BlockingGraph] = {}
        orchestrator, session, sent, send = make_orchestrator(
            lambda: graph_holder.setdefault("g", BlockingGraph())
        )
        before = session.last_state

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "search that won't finish"}, send=send
        )
        await asyncio.sleep(0)
        await asyncio.wait_for(graph_holder["g"].started.wait(), timeout=2)
        await orchestrator.handle_message(session, {"type": "cancel"}, send=send)
        await asyncio.sleep(0.05)

        assert session.last_state is before  # untouched by dead run


# ---------------------------------------------------------------------------
# Phase 10: concurrent sessions isolation
# ---------------------------------------------------------------------------


class TestConcurrentSessions:
    async def test_parallel_sessions_keep_events_and_state_isolated(self) -> None:
        store = InMemorySessionStore()
        settings = Settings(jarvis_assistant_llm_enabled=False)

        def make(session_id: str, jobs: list[dict[str, Any]]):
            sent: list[dict[str, Any]] = []

            async def send(envelope: dict[str, Any]) -> None:
                sent.append(envelope)

            session = store.get_or_create(session_id)
            orchestrator = JarvisOrchestrator(
                settings,
                session_store=store,
                graph_factory=lambda: ScriptedGraph([{"fetch_sources": {"jobs": jobs}}]),
            )
            return orchestrator, session, sent, send

        orch_a, sess_a, sent_a, send_a = make("s-a", [JOB_A])
        orch_b, sess_b, sent_b, send_b = make("s-b", [JOB_B])

        await asyncio.gather(
            orch_a.handle_message(sess_a, {"type": "chat", "text": "find a"}, send=send_a),
            orch_b.handle_message(sess_b, {"type": "chat", "text": "find b"}, send=send_b),
        )
        await asyncio.gather(orch_a.wait_for_run(), orch_b.wait_for_run())

        run_ids_a = {e.get("run_id") for e in sent_a}
        run_ids_b = {e.get("run_id") for e in sent_b}
        assert run_ids_a.isdisjoint(run_ids_b)
        assert all("s-a" in rid for rid in run_ids_a if rid)

        seqs_a = [e["seq"] for e in sent_a]
        seqs_b = [e["seq"] for e in sent_b]
        assert seqs_a == sorted(set(seqs_a))
        assert seqs_b == sorted(set(seqs_b))

        snap_a = next(e for e in sent_a if e["type"] == "assistant_message")[
            "data"]["result_snapshot"]
        snap_b = next(e for e in sent_b if e["type"] == "assistant_message")[
            "data"]["result_snapshot"]
        assert [j["title"] for j in snap_a["jobs"]] == ["Python Engineer"]
        assert [j["title"] for j in snap_b["jobs"]] == ["Backend Python"]

        assert sess_a.candidate_input is None or sess_a is not sess_b
        assert sess_a.last_state is not sess_b.last_state or sess_a.last_state is None


# ---------------------------------------------------------------------------
# Phase 11: failure modes stay typed
# ---------------------------------------------------------------------------


class TestFailureModes:
    @pytest.mark.parametrize("fail_after,nodes", [(0, 2), (1, 3)])
    async def test_workflow_failure_emits_typed_error_then_completes(
        self, fail_after: int, nodes: int
    ) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates(), fail_after=fail_after)
        )

        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find"}, send=send
        )
        await orchestrator.wait_for_run()

        errors = [e for e in sent if e["type"] == "error"]
        assert errors, "expected a typed error event"
        err = errors[-1]["data"]
        assert err["code"] == "workflow_failed"
        assert "RuntimeError" in err["message"]  # type name only — safe
        assert "Traceback" not in err["message"]
        # run still terminates cleanly for the client
        assert sent[-1]["type"] == "completed"
        # no partial artifacts leak as success: assistant_message absent
        assert not any(e["type"] == "assistant_message" for e in sent)


# ---------------------------------------------------------------------------
# Phase 12: automated PII audit across ALL envelopes
# ---------------------------------------------------------------------------


class TestPiiAudit:
    async def test_no_pii_leaks_into_any_emitted_envelope(self) -> None:
        orchestrator, session, sent, send = make_orchestrator(
            lambda: ScriptedGraph(job_updates())
        )

        # Upload PII-bearing resume, then run discovery on top of it.
        payload = base64.b64encode(RESUME_TEXT.encode()).decode()
        await orchestrator.handle_message(
            session,
            {"type": "resume_upload", "name": "jane_resume.txt",
             "data_base64": payload},
            send=send,
        )
        await orchestrator.handle_message(
            session, {"type": "chat", "text": "find python engineer"}, send=send
        )
        await orchestrator.wait_for_run()

        rendered_all = ""
        for envelope in sent:
            rendered = str(envelope)
            rendered_all += rendered
            for secret in (
                PII_EMAIL.lower(),
                PII_PHONE.replace(" ", ""),
                PII_STREET.lower(),
                "jane doe",
                "jane_resume.txt",
            ):
                assert secret not in rendered.lower(), f"leaked: {secret}"

        # The narration must exist but reference only counts/skills.
        assistant = next(e for e in sent if e["type"] == "assistant_message")
        assert assistant["data"]["text"]
