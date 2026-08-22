"""Deterministic 0-100 scoring with explainable breakdowns."""

from __future__ import annotations

from datetime import UTC, datetime

from app.ranking.features import extract_features
from app.ranking.preferences import SearchPreferences
from app.ranking.scorer import score_job

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def score(job, prefs_raw=None):
    features = extract_features(job, 0)
    return score_job(features, SearchPreferences.from_state(prefs_raw), now=NOW)


def make_job(**overrides):
    base = {
        "source": "lever",
        "source_job_id": "1",
        "title": "Machine Learning Engineer",
        "company": "Acme Inc",
        "location": "Bangalore",
        "description": "<p>python machine learning systems</p>",
        "requirements": None,
        "responsibilities": None,
        "employment_type": None,
        "salary": None,
        "source_created_at": "2026-08-22T10:00:00Z",
        "extra": {},
    }
    base.update(overrides)
    return base


class TestTitleComponent:
    def test_exact_role_match_scores_30(self) -> None:
        result = score(make_job(), {"soft": {"target_roles": ["Machine Learning Engineer"]}})

        assert result.breakdown["title"].points == 30
        assert result.breakdown["title"].status == "matched"

    def test_alias_match_scores_30(self) -> None:
        result = score(make_job(title="ML Engineer"), {"soft": {"target_roles": ["ML Engineer"]}})

        assert result.breakdown["title"].points == 30

    def test_related_title_partial_credit(self) -> None:
        result = score(
            make_job(title="Senior Machine Learning Platform Engineer"),
            {"soft": {"target_roles": ["machine learning engineer"]}},
        )

        points = result.breakdown["title"].points
        assert 6 <= points < 30

    def test_unrelated_title_zero(self) -> None:
        result = score(make_job(title="Sales Manager"), {"soft": {"target_roles": ["ml engineer"]}})

        assert result.breakdown["title"].points == 0

    def test_no_roles_requested_is_not_requested_full_points(self) -> None:
        result = score(make_job(), None)

        assert result.breakdown["title"].status == "not_requested"
        assert result.breakdown["title"].points == 30


class TestSkillComponent:
    def test_required_fraction(self) -> None:
        result = score(
            make_job(),
            {
                "soft": {
                    "required_skills": ["python", "pytorch"],
                }
            },
        )

        component = result.breakdown["skills"]["required"]
        assert component.points == 7.5  # 15 * 1/2

    def test_preferred_contributes_up_to_ten(self) -> None:
        result = score(
            make_job(description="<p>python pytorch docker kubernetes</p>"),
            {"soft": {"preferred_skills": ["docker", "kubernetes", "airflow"]}},
        )

        component = result.breakdown["skills"]["preferred"]
        assert component.points == pytest_approx(10 * 2 / 3)

    def test_missing_required_listed_for_explanation(self) -> None:
        result = score(
            make_job(),
            {"soft": {"required_skills": ["python", "pytorch"]}},
        )

        assert result.missing_required_skills == ("pytorch",)
        assert result.matched_skills == ("python",)


class TestLocationAndLevelComponents:
    def test_location_match_mismatch_unknown(self) -> None:
        match = score(make_job(location="Bangalore"), {"hard": {"locations": ["Bangalore"]}})
        mismatch = score(make_job(location="London"), {"hard": {"locations": ["Bangalore"]}})
        unknown = score(make_job(location=None), {"hard": {"locations": ["Bangalore"]}})

        assert match.breakdown["location"].points == 15
        assert mismatch.breakdown["location"].points == 0
        assert unknown.breakdown["location"].points == 7
        assert unknown.breakdown["location"].status == "neutral"

    def test_level_match_and_neutral_unknown(self) -> None:
        intern = score(
            make_job(title="ML Engineer Intern"),
            {"soft": {"prefer_internship_fresher": True}},
        )
        senior = score(
            make_job(title="Senior ML Engineer"),
            {"soft": {"prefer_internship_fresher": True}},
        )
        unknown = score(
            make_job(title="ML Engineer"),
            {"soft": {"prefer_internship_fresher": True}},
        )

        assert intern.breakdown["experience"].points == 10
        assert senior.breakdown["experience"].points == 0
        assert unknown.breakdown["experience"].points == 5
        assert unknown.breakdown["experience"].status == "neutral"


class TestFreshnessComponent:
    def test_tiered_freshness_from_source_created_at_only(self) -> None:
        fresh = score(make_job(source_created_at="2026-08-22T08:00:00Z"))      # 4h
        days_old = score(make_job(source_created_at="2026-08-20T00:00:00Z"))   # ~2.5d
        weeks_old = score(make_job(source_created_at="2026-08-12T00:00:00Z"))  # ~10.5d
        ancient = score(make_job(source_created_at="2025-01-01T00:00:00Z"))    # >30d

        assert fresh.breakdown["freshness"].points == 10
        assert days_old.breakdown["freshness"].points == 8
        assert weeks_old.breakdown["freshness"].points == 4
        assert ancient.breakdown["freshness"].points == 1

    def test_missing_timestamp_neutral_not_rewarded(self) -> None:
        result = score(make_job(source_created_at=None))

        assert result.breakdown["freshness"].points == 3
        assert result.breakdown["freshness"].reason == "posting date unavailable from source"

    def test_discovery_age_never_used_as_posting_age(self) -> None:
        """discovered_at exists but freshness stays neutral without source date."""
        job = make_job(
            source_created_at=None,
            discovered_at="2026-08-22T11:59:00Z",
        )
        result = score(job)

        assert result.breakdown["freshness"].points == 3


class TestEmploymentAndSalaryComponents:
    def test_employment_match_mismatch_unknown(self) -> None:
        matched = score(
            make_job(extra={"detected_extensions": {"schedule": "Internship"}}),
            {"hard": {"employment_types": ["internship"]}},
        )
        mismatched = score(
            make_job(extra={"detected_extensions": {"schedule": "Full-time"}}),
            {"hard": {"employment_types": ["internship"]}},
        )
        unknown = score(
            make_job(employment_type=None),
            {"hard": {"employment_types": ["internship"]}},
        )

        assert matched.breakdown["employment_type"].points == 5
        assert mismatched.breakdown["employment_type"].points == 0
        assert unknown.breakdown["employment_type"].points == 2.5
        assert unknown.breakdown["employment_type"].status == "neutral"

    def test_salary_meets_below_missing(self) -> None:
        meets = score(
            make_job(salary={"min_amount": 500000, "currency": "INR"}),
            {"soft": {"salary_min": "400000", "salary_currency": "inr"}},
        )
        below = score(
            make_job(salary={"min_amount": 100000, "currency": "INR"}),
            {"soft": {"salary_min": "400000", "salary_currency": "inr"}},
        )
        missing = score(make_job(salary=None), {"soft": {"salary_min": "400000"}})

        assert meets.breakdown["salary"].points == 5
        assert below.breakdown["salary"].points == 0
        assert missing.breakdown["salary"].points == 2.5


class TestTotalsAndTieBreaks:
    def test_total_equals_component_sum(self) -> None:
        result = score(
            make_job(),
            {
                "hard": {"locations": ["bangalore"], "max_age_hours": 24},
                "soft": {"target_roles": ["ml engineer"], "required_skills": ["python"]},
            },
        )

        total = sum(
            component.points for _, component in _flatten(result.breakdown)
        ) if False else sum(component.points for _, component in _iter(result.breakdown))
        assert result.total == round(total, 2)

    def test_deterministic_ordering_via_tie_key(self) -> None:
        fresh = make_job(
            source_job_id="fresh",
            source_created_at="2026-08-22T11:00:00Z",
        )
        older = make_job(
            source_job_id="older",
            source_created_at="2026-08-21T09:00:00Z",
        )

        fresh_score = score(fresh, {"soft": {"target_roles": ["ml engineer"]}})
        older_score = score(older, {"soft": {"target_roles": ["ml engineer"]}})

        assert fresh_score.tie_key < older_score.tie_key


def pytest_approx(value: float) -> float:
    return round(value, 2)


def _flatten(breakdown):
    yield from _iter(breakdown)


def _iter(breakdown):
    from app.ranking.scorer import ComponentResult

    for value in breakdown.values():
        if isinstance(value, ComponentResult):
            yield None, value
        elif isinstance(value, dict):
            yield from ((None, sub) for sub in value.values())
