"""LangGraph integration: fail-open ranking node after deduplication."""

from __future__ import annotations

from app.graph.workflow import DEDUP_NODE, RANK_NODE, build_workflow
from app.sources.base import FetchResult


def make_job(source="greenhouse", source_job_id="1", **overrides):
    job = {
        "source": source,
        "source_job_id": source_job_id,
        "title": "ML Engineer",
        "company": "Acme Inc",
        "location": "Bangalore",
        "description": "<p>python machine learning</p>",
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

    def __init__(self, jobs=()) -> None:
        self._jobs = tuple(jobs)

    async def fetch_jobs(self, preferences):
        from app.models.job import Job

        jobs = [job if isinstance(job, Job) else Job(**job) for job in self._jobs]
        return FetchResult(jobs=tuple(jobs))


PREFS = {
    "ranking": {
        "hard": {"locations": ["bangalore"]},
        "soft": {"target_roles": ["machine learning engineer"]},
    }
}


class TestRankingNodeIntegration:
    async def test_ranked_jobs_emitted_after_dedup_node(self) -> None:
        adapter = StubAdapter(
            jobs=[
                make_job(source_job_id="1"),
                make_job(
                    source="lever",
                    source_job_id="l9",
                    title="Senior ML Engineer",
                    location="Bangalore",
                    description="<p>python machine learning senior role</p>",
                ),
            ]
        )
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": PREFS})

        assert RANK_NODE in set(graph.get_graph().nodes.keys())
        ranked = state["ranked_jobs"]
        assert len(ranked) == 2  # dedup kept both distinct postings
        scores = [item["score"] for item in ranked]
        assert scores == sorted(scores, reverse=True)
        assert (
            ranked[0]["breakdown"]["title"]["points"]
            >= ranked[1]["breakdown"]["title"]["points"]
        )

    async def test_summary_histogram_present(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": PREFS})

        summary = state["ranking_summary"]
        assert summary["kept"] == len(state["ranked_jobs"])
        assert isinstance(summary["rejected_histogram"], dict)

    async def test_no_preferences_still_ranks_neutrally(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": {}})

        assert len(state["ranked_jobs"]) == 1

    async def test_fail_open_on_unexpected_ranking_failure(self, monkeypatch) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("ranking exploded")

        monkeypatch.setattr("app.graph.workflow.rank_jobs", boom)
        # Distinct requisitions so dedup keeps both before ranking runs.
        adapter = StubAdapter(
            jobs=[
                make_job(source_job_id="1", company="Alpha Corp"),
                make_job(
                    source="lever",
                    source_job_id="l2",
                    company="Beta Corp",
                    job_url="https://jobs.lever.co/beta/l2",
                ),
            ]
        )
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": PREFS})

        # Jobs preserved (post-dedup count); typed non-retryable error recorded.
        assert len(state["jobs"]) == 2
        (ranking_error,) = [e for e in state["errors"] if e["source"] == "ranking"]
        assert ranking_error["retryable"] is False
        warnings = [w for w in state.get("warnings") or [] if w["source"] == "ranking"]
        assert any(w["code"] == "ranking_failed" for w in warnings)
        assert "ranked_jobs" not in state

    async def test_upstream_errors_preserved_through_ranking(self) -> None:
        from app.sources.errors import SourceRateLimitError

        class FailingStub(StubAdapter):
            source_name = "failing"

            async def fetch_jobs(self, preferences):
                raise SourceRateLimitError("429", source="failing")

        ok = StubAdapter(jobs=[make_job()])
        graph = build_workflow([FailingStub(), ok])

        state = await graph.ainvoke({"search_preferences": PREFS})

        sources = {error["source"] for error in state["errors"]}
        assert "failing" in sources
        assert len(state["ranked_jobs"]) == 1

    async def test_dedup_then_rank_pipeline_order(self) -> None:
        """Dedup merges duplicates first; ranking sees the canonical cluster."""
        duplicate_a = make_job(source="greenhouse", source_job_id="g1")
        duplicate_b = make_job(
            source="lever",
            source_job_id="l1",
            job_url="https://jobs.lever.co/acme/l1",
        )
        adapter = StubAdapter(jobs=[duplicate_a, duplicate_b])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({"search_preferences": PREFS})

        assert len(state["jobs"]) == 1  # deduplicated first
        assert len(state["ranked_jobs"]) == 1
        assert DEDUP_NODE in set(graph.get_graph().nodes.keys())
