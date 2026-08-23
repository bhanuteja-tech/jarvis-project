"""Preference parsing: employment/level normalization, aliases, hard/soft."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ranking.preferences import (
    EmploymentType,
    ExperienceLevel,
    SearchPreferences,
    detect_level,
    normalize_employment,
    role_variants,
)


class TestEmploymentNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("FULL_TIME", EmploymentType.FULL_TIME),
            ("Full-time", EmploymentType.FULL_TIME),
            ("Regular Full Time (Salary)", EmploymentType.FULL_TIME),
            ("Part-time", EmploymentType.PART_TIME),
            ("Contract", EmploymentType.CONTRACT),
            ("CONTRACTOR", EmploymentType.CONTRACT),
            ("Internship", EmploymentType.INTERNSHIP),
            ("INTERN", EmploymentType.INTERNSHIP),
            ("Temporary", EmploymentType.TEMPORARY),
        ],
    )
    def test_verified_variants_map_correctly(self, raw: str, expected: EmploymentType) -> None:
        assert normalize_employment(raw) is expected

    def test_unknown_becomes_other_and_empty_none(self) -> None:
        assert normalize_employment("Volunteer position") is EmploymentType.OTHER
        assert normalize_employment("") is None
        assert normalize_employment(None) is None


class TestLevelDetection:
    def test_title_tokens_detect_levels(self) -> None:
        assert detect_level("Senior ML Engineer") is ExperienceLevel.SENIOR
        assert detect_level("Data Analyst Intern") is ExperienceLevel.INTERN
        assert detect_level("Fresher Java Developer") is ExperienceLevel.FRESHER
        assert detect_level("Principal Research Scientist") is ExperienceLevel.PRINCIPAL

    def test_no_signal_returns_none(self) -> None:
        assert detect_level("Platform Engineer") is None
        assert detect_level(None) is None


class TestRoleAliases:
    def test_declared_aliases_expand(self) -> None:
        variants = role_variants("Machine Learning Engineer")
        assert "ml engineer" in variants
        assert "machine learning developer" in variants

    def test_data_engineer_is_not_an_ml_alias(self) -> None:
        assert "data engineer" not in role_variants("Machine Learning Engineer")


class TestSearchPreferences:
    def test_nested_hard_soft_parsing(self) -> None:
        prefs = SearchPreferences.from_state(
            {
                "hard": {"locations": ["Bangalore"], "max_age_hours": 24},
                "soft": {
                    "target_roles": ["machine learning engineer"],
                    "required_skills": ["Python"],
                    "prefer_internship_fresher": True,
                },
            }
        )

        assert prefs.hard.locations == ["bangalore"]
        assert prefs.hard.max_age_hours == 24
        assert prefs.soft.prefer_internship_fresher is True
        assert prefs.soft.required_skills == ["Python"]

    def test_flat_keys_tolerated(self) -> None:
        prefs = SearchPreferences.from_state({"locations": ["Remote"], "limit": 10})

        assert prefs.hard.locations == ["remote"]
        assert prefs.soft.limit == 10

    def test_invalid_employment_values_dropped(self) -> None:
        prefs = SearchPreferences.from_state(
            {"hard": {"employment_types": ["full-time", "gibberish"]}}
        )

        assert prefs.hard.employment_types == [EmploymentType.FULL_TIME]

    def test_bad_salary_min_neutralized(self) -> None:
        prefs = SearchPreferences.from_state({"soft": {"salary_min": "not-a-number"}})

        assert prefs.soft.salary_min is None

    def test_empty_state_yields_defaults(self) -> None:
        prefs = SearchPreferences.from_state(None)

        assert prefs.soft.limit == 50
        assert prefs.hard.locations == []

    def test_limit_bounds_enforced(self) -> None:
        with pytest.raises(ValidationError):
            SearchPreferences.model_validate({"soft": {"limit": 0}})
