"""LangGraph integration: fail-open validation node after tailoring."""

from __future__ import annotations

from app.graph.workflow import (
    MATCHING_NODE,
    TAILOR_NODE,
    VALIDATION_NODE,
    build_workflow,
)
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
            "profile_id": "pid-v",
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


class TestValidationNodeIntegration:
    async def test_validation_report_emitted_after_tailoring(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python data engineer"},
                "candidate_profile": make_candidate_result(),
            }
        )

        assert VALIDATION_NODE in set(graph.get_graph().nodes.keys())
        report = state["validation_report"]
        assert report["overall_status"] in {"PASS", "WARN", "FAIL"}
        assert len(report["truth"]["checks"]) >= 9   # T1–T10 (+info rows)
        assert len(report["ats"]["checks"]) >= 8     # A1–A8
        assert state["matching_summary"]["evaluated"] >= 1

    async def test_no_tailored_resume_skips_validation_with_warning(
        self, monkeypatch
    ) -> None:
        # Make tailoring fail so tailored_resume is absent downstream.
        monkeypatch.setattr(
            "app.graph.workflow.tailor_resume",
            _fail_tailoring,
        )
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python"},
                "candidate_profile": make_candidate_result(),
            }
        )

        assert "validation_report" not in state
        warnings = [
            w for w in state.get("warnings") or []
            if w["source"] == "validation"
        ]
        assert any(w["code"] == "validation_skipped_no_resume" for w in warnings)

    async def test_fail_open_on_unexpected_validation_failure(
        self, monkeypatch
    ) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("validation exploded")

        monkeypatch.setattr("app.graph.workflow.validate_resume_service", boom)
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
        assert "tailored_resume" in state
        (validation_error,) = [
            e for e in state["errors"] if e["source"] == "validation"
        ]
        assert validation_error["retryable"] is False
        warnings = [w for w in state.get("warnings") or []
                    if w["source"] == "validation"]
        assert any(w["code"] == "validation_failed" for w in warnings)
        assert "validation_report" not in state


async def _fail_tailoring(*_args, **_kwargs):
    raise RuntimeError("tailoring intentionally failed")
