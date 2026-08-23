"""Orchestrator: event ordering, narration, PII exclusion, cancellation."""

from __future__ import annotations

from app.config.settings import Settings
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore


class FakeGraph:
    """Minimal stand-in for the compiled workflow."""

    def __init__(self, updates) -> None:
        self._updates = list(updates)

    async def astream(self, _state, stream_mode=None):
        assert stream_mode == "updates"
        for update in self._updates:
            yield update


def make_orchestrator(updates, **settings_overrides):
    sent: list[dict] = []

    async def send(envelope):
        sent.append(envelope)

    settings = Settings(jarvis_assistant_llm_enabled=False, **settings_overrides)
    store = InMemorySessionStore()
    session = store.get_or_create("s1")

    orchestrator = JarvisOrchestrator(
        settings,
        session_store=store,
        graph_factory=lambda: FakeGraph(updates),
    )
    return orchestrator, session, sent


GOOD_UPDATES = [
    {
        "fetch_sources": {
            "jobs": [
                {
                    "source": "greenhouse",
                    "source_job_id": "1",
                    "title": "Data Engineer",
                    "company": "TargetCo",
                    "job_url": "https://x/1",
                },
            ]
        }
    },
    {
        "deduplicate_jobs": {
            "jobs": [
                {
                    "source": "greenhouse",
                    "source_job_id": "1",
                    "title": "Data Engineer",
                    "company": "TargetCo",
                    "job_url": "https://x/1",
                },
            ]
        }
    },
    {"rank_jobs": {"ranked_jobs": [{"job_index": 0, "score": 70}]}, "ranking_summary": {}},
    {"analyze_jd": {"jd_analyses": []}, "analysis_errors": []},
    {
        "match_candidate_to_jobs": {
            "match_results": [
                {"job_index": 0, "score": 70, "tier": "strong", "confidence": "medium"}
            ]
        },
        "matching_summary": {},
    },
    {
        "tailor_resume": {
            "status": "tailored",
            "resume": {
                "target_job_index": 0,
                "summary": {
                    "text": "Engineer focused on python.",
                    "evidence_refs": ["resume.experience[0].title"],
                },
                "skills": [],
                "experience": [],
                "projects": [],
                "education": [],
                "certifications": [],
                "changes": [],
                "unaddressed_jd_requirements": ["docker"],
                "warnings": [],
                "metadata": {},
            },
        }
    },
    {"validate_resume": {"overall_status": "WARN"}},
]


async def run_chat(text="find python engineer in berlin", updates=GOOD_UPDATES):
    orchestrator, session, sent = make_orchestrator(
        updates,
        candidate_redact_pii=True,
    )
    session.candidate_input = None

    async def send(envelope):
        sent.append(envelope)

    await orchestrator.handle_message(session, {"type": "chat", "text": text}, send=send)
    return sent, session


class TestEventOrdering:
    async def test_event_sequence(self) -> None:
        sent, _session = await run_chat()

        types = [envelope["type"] for envelope in sent]
        assert types[0] == "agent_started"
        assert "workflow_node_completed" in types
        assert "assistant_message" in types
        assert types[-1] in {"completed"}

        # seq strictly increasing
        seqs = [envelope["seq"] for envelope in sent]
        assert seqs == sorted(seqs)

    async def test_node_events_emitted_for_each_completed_node(self) -> None:
        sent, _session = await run_chat()
        nodes = [e["data"].get("node") for e in sent if e["type"] == "workflow_node_completed"]

        assert set(nodes) >= {"fetch_sources", "rank_jobs", "tailor_resume"}


class TestNarration:
    async def test_reply_mentions_counts_and_top_match(self) -> None:
        sent, _session = await run_chat()

        assistant = next(e for e in sent if e["type"] == "assistant_message")
        text = assistant["data"]["text"]
        assert "1 job(s)" in text
        assert "70" in text

    async def test_no_pii_in_events(self) -> None:
        sent, _session = await run_chat()

        for envelope in sent:
            rendered = str(envelope)
            assert "jane" not in rendered.lower()
            assert "@example.com" not in rendered


class TestResumeUpload:
    async def test_upload_stores_candidate_input(self) -> None:
        orchestrator, session, sent = make_orchestrator([])

        async def send(envelope):
            sent.append(envelope)

        await orchestrator.handle_message(
            session,
            {
                "type": "resume_upload",
                "name": "resume.txt",
                "content": "Python engineer with sql experience.",
            },
            send=send,
        )

        assert session.candidate_input is not None
        tool_completed = [e for e in sent if e["type"] == "tool_completed"]
        assert tool_completed and tool_completed[0]["data"]["tool"] == "set_resume"

    async def test_pdf_rejected_with_unsupported_format(self) -> None:
        orchestrator, session, sent = make_orchestrator([])

        async def send(envelope):
            sent.append(envelope)

        await orchestrator.handle_message(
            session,
            {"type": "resume_upload", "name": "resume.pdf",
             "content": "%PDF-1.4 fake"},
            send=send,
        )

        errors = [e for e in sent if e["type"] == "error"]
        assert errors and errors[0]["data"]["code"] == "unsupported_format"
