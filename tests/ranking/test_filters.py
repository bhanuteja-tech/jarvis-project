"""Hard-requirement filtering: missing data never rejects."""

from __future__ import annotations

from datetime import UTC, datetime

from app.ranking.features import extract_features
from app.ranking.filters import apply_hard_filters
from app.ranking.preferences import (
    EmploymentType,
    ExperienceLevel,
    HardRequirements,
)

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def make_features(**overrides):
    job = {
        "source": "lever",
        "source_job_id": "1",
        "title": "ML Engineer",
        "company": "Acme Inc",
        "location": "Bangalore",
        "description": "<p>python machine learning</p>",
        "employment_type": None,
        "source_created_at": "2026-08-22T08:00:00Z",
        "extra": {},
    }
    job.update(overrides)
    return extract_features(job, 0)


class TestLocationFilter:
    def test_matching_location_passes(self) -> None:
        outcome = apply_hard_filters(
            make_features(), HardRequirements(locations=["bangalore"]), now=NOW
        )

        assert outcome.passed is True
        assert outcome.gaps == ()

    def test_mismatched_location_rejected(self) -> None:
        outcome = apply_hard_filters(
            make_features(location="London"),
            HardRequirements(locations=["bangalore"]),
            now=NOW,
        )

        assert outcome.passed is False
        assert outcome.failed_reason == "location_mismatch"

    def test_unknown_location_kept_with_gap(self) -> None:
        outcome = apply_hard_filters(
            make_features(location=None),
            HardRequirements(locations=["bangalore"]),
            now=NOW,
        )

        assert outcome.passed is True
        assert "location" in outcome.gaps


class TestEmploymentAndLevelFilters:
    def test_unknown_employment_kept_with_gap(self) -> None:
        outcome = apply_hard_filters(
            make_features(employment_type=None),
            HardRequirements(employment_types=[EmploymentType.INTERNSHIP]),
            now=NOW,
        )

        assert outcome.passed is True
        assert "employment_type" in outcome.gaps

    def test_known_employment_mismatch_rejected(self) -> None:
        features = make_features(
            employment_type="Full-time",
            extra={"detected_extensions": {"schedule": "Full-time"}},
        )
        outcome = apply_hard_filters(
            features,
            HardRequirements(employment_types=[EmploymentType.INTERNSHIP]),
            now=NOW,
        )

        # schedule fallback makes the type known => positive mismatch.
        assert outcome.passed is False
        assert outcome.failed_reason == "employment_type_mismatch"

    def test_level_detected_and_conflicting_rejected(self) -> None:
        features = make_features(title="Senior ML Engineer")
        outcome = apply_hard_filters(
            features,
            HardRequirements(experience_levels=[ExperienceLevel.INTERN]),
            now=NOW,
        )

        assert outcome.passed is False
        assert outcome.failed_reason == "experience_level_mismatch"

    def test_level_unknown_kept_with_gap(self) -> None:
        outcome = apply_hard_filters(
            make_features(title="ML Engineer"),
            HardRequirements(experience_levels=[ExperienceLevel.INTERN]),
            now=NOW,
        )

        assert outcome.passed is True
        assert "experience_level" in outcome.gaps


class TestFreshnessFilter:
    def test_within_cutoff_passes_without_gap(self) -> None:
        outcome = apply_hard_filters(
            make_features(),
            HardRequirements(max_age_hours=24),
            now=NOW,
        )

        assert outcome.passed is True
        assert outcome.gaps == ()

    def test_older_than_cutoff_rejected(self) -> None:
        outcome = apply_hard_filters(
            make_features(source_created_at="2026-08-01T00:00:00Z"),
            HardRequirements(max_age_hours=24),
            now=NOW,
        )

        assert outcome.passed is False
        assert outcome.failed_reason == "too_old"

    def test_missing_timestamp_never_rejected_locked_principle(self) -> None:
        outcome = apply_hard_filters(
            make_features(source_created_at=None),
            HardRequirements(max_age_hours=24),
            now=NOW,
        )

        assert outcome.passed is True
        assert "freshness_unknown" in outcome.gaps


class TestExclusions:
    def test_excluded_company_rejected(self) -> None:
        outcome = apply_hard_filters(
            make_features(company="Acme Inc"),
            HardRequirements(exclude_companies=["acme"]),
            now=NOW,
        )

        assert outcome.passed is False
        assert outcome.failed_reason == "excluded_company"

    def test_excluded_keyword_in_description_rejected(self) -> None:
        outcome = apply_hard_filters(
            make_features(description="<p>onsite role with unpaid overtime</p>"),
            HardRequirements(exclude_keywords=["unpaid"]),
            now=NOW,
        )

        assert outcome.passed is False
        assert outcome.failed_reason == "excluded_keyword"
