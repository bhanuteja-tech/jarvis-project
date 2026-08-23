"""LangGraph integration: fail-open tailoring node after matching."""

from __future__ import annotations

from app.graph.workflow import MATCHING_NODE, TAILOR_NODE, build_workflow
from app.sources.base import FetchResult


def make_job(source="greenhouse", source_job_id="1", **overrides):
    job = {
        "source": source,
        "source_job_id": source_job_id,
        "title": "Data Engineer",
        "company": "TargetCo",
        "location": "Remote",
        "description": "<p>python data engineering</p>",
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


def make_candidate_result():
    return {
        "status": "PARSED",
        "profile": {
            "profile_id": "pid-t",
            "skills": {"status": "explicit", "items": [
                {"name": "python", "matched_as": "Python",
                 "category": "language"},
            ]},
            "experience": {"status": "explicit", "total_years": 5.0,
                           "items": [
                {"title": "Data Engineer", "company": "Acme",
                 "highlights": ["Built python pipelines"],
                 "duration_months": 60},
            ]},
            "education": {"items": []},
            "certifications": {"items": []},
            "projects": {"items": []},
            "preferences": {},
            "summary": {"text": None},
        },
    }


class StubAdapter:
    source_name = "stub"

    def __init__(self, jobs=()) -> None:
        self._jobs = tuple(jobs)

    async def fetch_jobs(self, preferences):
        from app.models.job import Job

        jobs = [job if isinstance(job, Job) else Job(**job) for job in self._jobs]
        return FetchResult(jobs=tuple(jobs))


class TestTailoringNodeIntegration:
    async def test_tailored_resume_emitted_after_matching_node(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python engineer resume"},
                "candidate_profile": make_candidate_result(),
            }
        )

        assert TAILOR_NODE in set(graph.get_graph().nodes.keys())
        assert MATCHING_NODE in set(graph.get_graph().nodes.keys())
        tailored = state["tailored_resume"]
        assert tailored["status"] in {"tailored", "partial"}
        assert tailored["resume"]["target_job_index"] == 0

    async def test_no_candidate_skips_tailoring_with_warning(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({})

        assert "tailored_resume" not in state
        warnings = [w for w in state.get("warnings") or []
                    if w["source"] == "tailoring"]
        assert any(w["code"] == "tailoring_skipped_no_candidate" for w in warnings)

    async def test_fail_open_on_unexpected_tailoring_failure(
        self, monkeypatch
    ) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("tailoring exploded")

        monkeypatch.setattr("app.graph.workflow.tailor_resume", boom)
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python"},
                "candidate_profile": make_candidate_result(),
            }
        )

        # Prior phases preserved.
        assert len(state["jobs"]) == 1
        assert len(state["match_results"]) >= 1
        (tailoring_error,) = [
            e for e in state["errors"] if e["source"] == "tailoring"
        ]
        assert tailoring_error["retryable"] is False
        warnings = [w for w in state.get("warnings") or []
                    if w["source"] == "tailoring"]
        assert any(w["code"] == "tailoring_failed" for w in warnings)
        assert "tailored_resume" not in state
