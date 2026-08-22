"""LangGraph integration: fail-open matching node after JD analysis."""

from __future__ import annotations

from app.graph.workflow import MATCHING_NODE, build_workflow
from app.sources.base import FetchResult


def make_job(source="greenhouse", source_job_id="1", **overrides):
    job = {
        "source": source,
        "source_job_id": source_job_id,
        "title": "ML Engineer",
        "company": "Acme Inc",
        "location": "Remote",
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


def make_candidate_profile_result():
    """Phase-3-shaped CandidateResult dict for a python/remote candidate."""
    return {
        "status": "PARSED",
        "profile": {
            "profile_id": "abc123",
            "source_format": "plain_text",
            "identity": {"status": "inferred", "full_name": "Jane Doe"},
            "contact": {"status": "explicit", "pii": True,
                        "emails": ["jane@example.com"], "phones": [],
                        "links": [], "evidence": []},
            "summary": {"status": "unknown", "text": None, "evidence": []},
            "skills": {
                "status": "explicit",
                "items": [
                    {"name": "python", "matched_as": "Python",
                     "category": "language"},
                    {"name": "machine learning", "matched_as": "machine learning",
                     "category": "concept"},
                ],
            },
            "experience": {
                "status": "explicit",
                "total_years": 6.0,
                "items": [
                    {"title": "Senior ML Engineer", "company": "Beta",
                     "location": None, "start_raw": "Jan 2020",
                     "end_raw": "Present", "start_iso": "2020-01-01",
                     "end_iso": "2026-08-01", "is_current": True,
                     "duration_months": 80, "highlights": [],
                     "skills_in_role": [
                         {"name": "docker", "matched_as": "Docker",
                          "category": "tool"}
                     ],
                     "evidence": {"text": "Jan 2020 - Present",
                                  "field": "resume.experience",
                                  "method": "deterministic",
                                  "confidence": "high", "line": None}},
                ],
            },
            "education": {"status": "explicit", "items": [
                {"degree": "bachelor", "degree_raw": "BSc",
                 "field_of_study": "Computer Science",
                 "institution": "Acme University",
                 "graduation_year": 2015,
                 "evidence": {"text": "BSc in Computer Science",
                              "field": "resume.education",
                              "method": "deterministic",
                              "confidence": "medium", "line": None}},
            ]},
            "certifications": {"status": "unknown", "items": []},
            "projects": {"status": "unknown", "items": []},
            "preferences": {
                "status": "explicit",
                "locations": ["berlin"],
                "remote": True,
                "relocation": True,
                "employment_types": ["full_time"],
                "salary_min": {"amount": 90000.0,
                               "currency": "USD", "period": "year"},
                "evidence": [],
            },
            "coverage": {"sections_found": ["skills", "experience"],
                         "unrecognized_headings": 0},
            "metadata": {"source_format": "plain_text", "text_chars": 500,
                         "truncated": False, "duration_ms": 1.0},
            "redacted": False,
            "warnings": [],
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


class TestMatchingNodeIntegration:
    async def test_match_results_emitted_after_jd_node(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python ml engineer"},
                "candidate_profile": make_candidate_profile_result(),
            }
        )

        assert MATCHING_NODE in set(graph.get_graph().nodes.keys())
        assert len(state["match_results"]) == 1
        match = state["match_results"][0]
        assert match["job_index"] == 0
        assert match["tier"] in {"strong", "moderate", "weak"}
        assert "skills_required" in match["breakdown"]
        assert state["matching_summary"]["evaluated"] == 1

    async def test_no_candidate_profile_skips_matching_with_warning(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke({})

        assert "match_results" not in state
        warnings = [w for w in state.get("warnings") or [] if w["source"] == "matching"]
        assert any(w["code"] == "matching_skipped_no_candidate" for w in warnings)

    async def test_failed_candidate_skips_matching(self) -> None:
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])
        failed = {"status": "FAILED", "profile": None,
                  "reason": "empty_resume"}

        state = await graph.ainvoke(
            {"candidate_input": {"text": ""},
             "candidate_profile": failed}
        )

        assert "match_results" not in state
        warnings = [w for w in state.get("warnings") or [] if w["source"] == "matching"]
        assert any(
            w["code"] == "matching_skipped_no_candidate" and
            "FAILED" in w["message"] or "unusable" in w["message"]
            for w in warnings
        )

    async def test_fail_open_on_unexpected_matching_failure(self, monkeypatch) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("matching exploded")

        monkeypatch.setattr("app.graph.workflow.match_jobs", boom)
        adapter = StubAdapter(jobs=[make_job()])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python"},
                "candidate_profile": make_candidate_profile_result(),
            }
        )

        # All prior state preserved.
        assert len(state["jobs"]) == 1
        assert len(state["ranked_jobs"]) == 1
        (matching_error,) = [e for e in state["errors"] if e["source"] == "matching"]
        assert matching_error["retryable"] is False
        warnings = [w for w in state.get("warnings") or [] if w["source"] == "matching"]
        assert any(w["code"] == "matching_failed" for w in warnings)
        assert "match_results" not in state

    async def test_full_pipeline_order_dedup_rank_jd_match(self) -> None:
        duplicate_a = make_job(source="greenhouse", source_job_id="g1")
        duplicate_b = make_job(
            source="lever",
            source_job_id="l1",
            job_url="https://jobs.lever.co/acme/l1",
        )
        adapter = StubAdapter(jobs=[duplicate_a, duplicate_b])
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "candidate_input": {"text": "python"},
                "candidate_profile": make_candidate_profile_result(),
            }
        )

        # Dedup merged the duplicates; ranking/JD/matching each see one job.
        assert len(state["jobs"]) == 1
        assert len(state["ranked_jobs"]) == 1
        assert len(state["jd_analyses"]) >= 1
        assert len(state["match_results"]) == 1
