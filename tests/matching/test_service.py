"""End-to-end matching service: indexing, ordering, summary."""

from __future__ import annotations

from app.matching.service import match_jobs
from tests.matching.test_views import ANALYZED, make_candidate_result, make_job


def run(jobs, analyses=None, candidate=None):
    candidate = candidate or make_candidate_result()
    return match_jobs(candidate, jobs, ranked_jobs=None, jd_analyses=analyses)


class TestServiceBehavior:
    def test_all_jobs_evaluated_and_sorted_desc(self) -> None:
        strong_job = make_job(source_job_id="strong")  # matches ANALYZED well
        weak_job = make_job(
            source="lever",
            source_job_id="weak",
            title="Sales Manager",
            location="London",
        )
        weak_analysis = {
            "status": "ANALYZED",
            "job_index": 1,
            "analysis": {
                "skills": {"required": [{"name": "salesforce"}]},
                "experience": {"min_years": 1},
                "work_arrangement": {"mode": "onsite"},
                "location": {"job_location": "London"},
                "salary": {},
            },
        }

        outcome = run([strong_job, weak_job], [ANALYZED, weak_analysis])

        scores = [m.score for m in outcome.match_results]
        assert scores == sorted(scores, reverse=True)
        assert outcome.summary.evaluated == 2
        assert outcome.summary.tiers["strong"] >= 1
        assert outcome.skipped_reason is None

    def test_tie_break_by_index_when_scores_equal(self) -> None:
        job_a = make_job()
        job_b = make_job()

        outcome = run([job_a, job_b], [ANALYZED, ANALYZED])

        assert [m.job_index for m in outcome.match_results] == [0, 1]

    def test_jobs_without_analysis_counted(self) -> None:
        jobs = [make_job(), make_job(), make_job()]
        outcome = run(jobs, [ANALYZED])

        assert outcome.summary.jobs_without_analysis == 2
        missing = [
            m for m in outcome.match_results if "jd_analysis_missing" in m.gaps
        ]
        assert len(missing) == 2

    def test_deterministic_repeat_runs(self) -> None:
        jobs = [make_job(), make_job(source_job_id="2", location=None)]
        analyses = [ANALYZED, None]

        first = run(jobs, analyses)
        second = run(jobs, analyses)

        assert [m.to_dict() for m in first.match_results] == [
            m.to_dict() for m in second.match_results
        ]

    def test_input_jobs_never_mutated(self) -> None:
        job = make_job()
        snapshot = dict(job)

        run([job], [ANALYZED])

        assert job == snapshot


class TestCandidateSkipPaths:
    def test_missing_candidate_skips(self) -> None:
        outcome = run([make_job()], candidate={"status": "SKIPPED", "profile": None})

        assert outcome.skipped_reason == "candidate_profile_unusable"
        assert outcome.match_results == []

    def test_failed_candidate_skips(self) -> None:
        outcome = run(
            [make_job()],
            candidate={"status": "FAILED", "profile": None, "reason": "empty_resume"},
        )

        assert outcome.skipped_reason == "candidate_profile_unusable"

    async def test_none_candidate_object(self) -> None:
        from app.matching.views import build_candidate_view

        view = build_candidate_view(None)
        assert view.usable is False
