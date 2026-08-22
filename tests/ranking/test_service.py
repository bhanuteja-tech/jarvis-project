"""End-to-end ranking service behavior (filter → score → sort → limit)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.ranking.service import rank_jobs

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def make_job(**overrides):
    base = {
        "source": "lever",
        "source_job_id": "1",
        "title": "Software Engineer",
        "company": "Acme Inc",
        "location": "New York, NY",
        "description": "<p>general software work</p>",
        "requirements": None,
        "responsibilities": None,
        "employment_type": None,
        "salary": None,
        "source_created_at": None,
        "discovered_at": "2026-08-22T10:00:00Z",
        "extra": {},
    }
    base.update(overrides)
    return base


PREFS = {
    "hard": {"locations": ["bangalore"], "max_age_hours": 24},
    "soft": {
        "target_roles": ["machine learning engineer"],
        "required_skills": ["python"],
        "prefer_internship_fresher": True,
    },
}


class TestRankingService:
    def test_example_query_end_to_end_ordering(self) -> None:
        """'recent ML engineer jobs in Bangalore, preferably internships, 24h'."""
        perfect = make_job(
            source_job_id="perfect",
            title="ML Engineer Intern",
            location="Bangalore",
            description="<p>python machine learning internship for freshers</p>",
            extra={"detected_extensions": {"schedule": "Internship"}},
            source_created_at="2026-08-22T09:00:00Z",
        )
        wrong_city = make_job(
            source_job_id="wrong-city",
            title="ML Engineer",
            location="London",
            description="<p>python machine learning</p>",
            source_created_at="2026-08-22T09:00:00Z",
        )
        stale = make_job(
            source_job_id="stale",
            title="ML Engineer Intern",
            location="Bangalore",
            source_created_at="2026-07-01T00:00:00Z",
        )
        unrelated = make_job(source_job_id="unrelated", company="Beta Corp")

        outcome = rank_jobs([perfect, wrong_city, stale, unrelated], PREFS, now=NOW)

        indices = [ranked.job_index for ranked in outcome.ranked_jobs]
        assert indices[0] == 0  # perfect match first
        # Both the wrong-city job AND the unrelated NY job fail location.
        assert outcome.summary.rejected_histogram.get("location_mismatch") == 2
        assert outcome.summary.rejected_histogram.get("too_old") == 1
        assert outcome.summary.kept == 1

    def test_ranked_wrapper_references_job_index_without_mutating_jobs(self) -> None:
        generic = make_job(source_job_id="0")
        ml_job = make_job(
            source="lever",
            source_job_id="1",
            title="ML Engineer",
            location="Bangalore",
        )
        jobs = [generic, ml_job]

        outcome = rank_jobs(jobs, {"soft": {"target_roles": ["ml engineer"]}}, now=NOW)

        # Service never reorders or mutates the input list.
        assert [job["source_job_id"] for job in jobs] == ["0", "1"]
        top = outcome.ranked_jobs[0]
        assert top.job_index == 1  # the ML job ranks above generic SWE

    def test_limit_caps_results(self) -> None:
        jobs = [
            make_job(source_job_id=str(i), title="ML Engineer", location="Bangalore")
            for i in range(30)
        ]

        outcome = rank_jobs(jobs, {"soft": {"limit": 5, "target_roles": ["ml engineer"]}}, now=NOW)

        assert len(outcome.ranked_jobs) == 5
        assert outcome.summary.limit == 5

    def test_empty_input(self) -> None:
        outcome = rank_jobs([], PREFS, now=NOW)

        assert outcome.ranked_jobs == []
        assert outcome.summary.kept == 0

    def test_single_job_survives_with_full_breakdown(self) -> None:
        outcome = rank_jobs([make_job(location="Bangalore")], PREFS, now=NOW)

        assert len(outcome.ranked_jobs) == 1
        breakdown = outcome.ranked_jobs[0].breakdown
        for component in ("title", "skills", "location", "experience", "freshness"):
            assert component in breakdown

    def test_deterministic_repeat_runs(self) -> None:
        jobs = [
            make_job(
                source_job_id=str(i),
                title=f"ML Engineer {i}",
                location="Bangalore",
                description=f"<p>python ml role number {i}</p>",
                source_created_at="2026-08-22T08:00:00Z",
            )
            for i in range(8)
        ]

        first = rank_jobs(jobs, {"soft": {"target_roles": ["ml engineer"]}}, now=NOW)
        second = rank_jobs(jobs, {"soft": {"target_roles": ["ml engineer"]}}, now=NOW)

        assert [r.job_index for r in first.ranked_jobs] == [
            r.job_index for r in second.ranked_jobs
        ]

    def test_no_preferences_neutral_full_scores(self) -> None:
        jobs = [make_job(), make_job(source_job_id="2")]

        outcome = rank_jobs(jobs, None, now=NOW)

        assert len(outcome.ranked_jobs) == 2
        # Unspecified constraints award full points (not_requested); the only
        # deduction is evidence-based freshness neutrality (no source date).
        scores = {ranked.score for ranked in outcome.ranked_jobs}
        assert scores == {93.0}
        assert all(
            ranked.breakdown["freshness"].status == "neutral"
            for ranked in outcome.ranked_jobs
        )
