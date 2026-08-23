"""LangGraph integration: fail-open dedup node between fetch and END."""

from __future__ import annotations

from app.graph.workflow import DEDUP_NODE, build_workflow
from app.sources.base import FetchResult


def make_job(source="greenhouse", source_job_id="1", **overrides):
    job = {
        "source": source,
        "source_job_id": source_job_id,
        "title": "Software Engineer",
        "company": "Acme Inc",
        "location": "New York, NY",
        "description": "<p>Build things</p>",
        "requirements": None,
        "responsibilities": None,
        "employment_type": None,
        "salary": None,
        "job_url": f"https://boards.greenhouse.io/acme/jobs/{source_job_id}",
        "apply_url": None,
        "source_created_at": None,
        "source_updated_at": None,
        "discovered_at": "2026-08-22T10:00:00Z",
        "fetched_at": "2026-08-22T10:00:00Z",
        "extra": {},
    }
    job.update(overrides)
    return job


class StubAdapter:
    source_name = "stub"

    def __init__(self, jobs=(), error: Exception | None = None) -> None:
        self._jobs = tuple(jobs)
        self._error = error

    async def fetch_jobs(self, preferences):
        from app.models.job import Job

        if self._error is not None:
            raise self._error
        jobs = [job if isinstance(job, Job) else Job(**job) for job in self._jobs]
        return FetchResult(jobs=tuple(jobs))


class TestDedupNodeIntegration:
    async def test_duplicate_jobs_merge_in_state(self) -> None:
        adapter_a = StubAdapter(
            jobs=[
                make_job(
                    source="greenhouse",
                    source_job_id="g1",
                    job_url="https://boards.greenhouse.io/acme/jobs/g1",
                )
            ]
        )
        adapter_b = StubAdapter(
            jobs=[
                make_job(
                    source="lever",
                    source_job_id="l1",
                    title="Software Engineer",
                    company="Acme Inc",
                    location="New York, NY",
                    job_url="https://jobs.lever.co/acme/l1",
                )
            ]
        )
        graph = build_workflow([adapter_a, adapter_b])

        state = await graph.ainvoke({"search_preferences": {}})

        assert len(state["jobs"]) == 1
        dedup_meta = state["jobs"][0]["extra"]["dedup"]
        assert dedup_meta["cluster_size"] == 2

    async def test_upstream_errors_preserved_alongside_dedup(self) -> None:
        from app.sources.errors import SourceRateLimitError

        failing = StubAdapter(error=SourceRateLimitError("429", source="lever"))
        succeeding = StubAdapter(jobs=[make_job()])
        graph = build_workflow([failing, succeeding])

        state = await graph.ainvoke({"search_preferences": {}})

        kinds = [error["source"] for error in state["errors"]]
        assert "lever" in kinds
        assert len(state["jobs"]) == 1

    async def test_fail_open_passthrough_on_unexpected_dedup_failure(self, monkeypatch) -> None:
        def boom(_jobs):
            raise RuntimeError("dedup exploded")

        monkeypatch.setattr("app.graph.workflow.dedupe_jobs", boom)
        adapter = StubAdapter(jobs=[make_job(), make_job(source_job_id="2")])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": {}})

        # Jobs passed through unmerged; typed non-retryable error recorded.
        assert len(state["jobs"]) == 2
        (dedup_error,) = [e for e in state["errors"] if e["source"] == "dedup"]
        assert dedup_error["kind"] == "RuntimeError"
        assert dedup_error["retryable"] is False
        warnings = [w for w in state.get("warnings") or [] if w["source"] == "dedup"]
        assert any(w["code"] == "dedup_failed" for w in warnings)

    async def test_empty_and_single_inputs_are_safe(self) -> None:
        empty_graph = build_workflow([StubAdapter(jobs=[])])
        state = await empty_graph.ainvoke({"search_preferences": {}})
        assert state["jobs"] == []

        single_graph = build_workflow([StubAdapter(jobs=[make_job()])])
        state = await single_graph.ainvoke({"search_preferences": {}})
        assert len(state["jobs"]) == 1
        assert DEDUP_NODE in single_game_node_names(single_graph)


def single_game_node_names(graph):
    try:
        return set(graph.get_graph().nodes.keys())
    except Exception:  # pragma: no cover - structural introspection fallback
        return {DEDUP_NODE}
