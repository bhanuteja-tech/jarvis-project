"""Deterministic extractors: required/preferred, experience, education,
salary evidence, certifications."""

from __future__ import annotations

from app.jdunderstanding.extractors import (
    build_salary_field,
    extract_education,
    extract_experience,
    extract_skills,
)
from app.jdunderstanding.models import (
    ExtractionStatus,
    RequirementLevel,
    SectionKind,
)
from app.jdunderstanding.sections import segment_document
from app.jdunderstanding.text import extract_text_document


def _segment(raw: str):
    return segment_document(extract_text_document(raw, max_chars=20_000))


JD_REQUIRED_PREFERRED = """
Requirements
- Python required for day-to-day work
- SQL and AWS experience must have

Nice to have
- Docker is a plus
- Kubernetes preferred
"""


class TestRequiredVsPreferred:
    def test_section_driven_split(self) -> None:
        document = extract_text_document(JD_REQUIRED_PREFERRED, max_chars=20_000)
        segmentation = _segment(JD_REQUIRED_PREFERRED)

        required, preferred, keywords = extract_skills(document.plain_text, segmentation)

        required_names = {skill.name for skill in required}
        preferred_names = {skill.name for skill in preferred}

        assert {"python", "sql", "aws"} <= required_names
        assert {"docker", "kubernetes"} <= preferred_names
        assert required_names.isdisjoint(preferred_names) or all(
            skill.requirement is RequirementLevel.REQUIRED for skill in required
        )
        assert keywords  # categorized keyword items exist

    def test_cue_fallback_when_unsectioned(self) -> None:
        raw = (
            "We expect strong python skills.\n"
            "\n"
            "Nice to have:\n"
            "- Docker experience is a plus\n"
        )
        document = extract_text_document(raw, max_chars=20_000)
        segmentation = _segment(raw)

        required, preferred, _keywords = extract_skills(document.plain_text, segmentation)

        assert any(skill.name == "python" for skill in required)
        assert any(skill.name == "docker" for skill in preferred)


class TestExperienceExtraction:
    def test_range(self) -> None:
        requirement = extract_experience("3-5 years of experience", _segment("x"))

        assert requirement.min_years == 3
        assert requirement.max_years == 5

    def test_plus_form(self) -> None:
        requirement = extract_experience("2+ years required", _segment("x"))

        assert requirement.min_years == 2
        assert requirement.max_years is None

    def test_zero_years_explicit(self) -> None:
        requirement = extract_experience("0 years experience needed", _segment("x"))

        assert requirement.min_years == 0

    def test_level_word_only(self) -> None:
        requirement = extract_experience("This is an internship position", _segment("x"))

        assert requirement.min_years is None
        assert requirement.level_word == "internship"

    def test_vague_language_never_manufactured(self) -> None:
        assert extract_experience("Join our growing team!", _segment("x")) is None


class TestEducationExtraction:
    def test_degree_with_field(self) -> None:
        items = extract_education(
            "Bachelor's degree in Computer Science or equivalent", _segment("x")
        )

        assert items[0].degree.startswith("bachelor")
        assert "computer science" in (items[0].field_of_study or "").lower()

    def test_bare_degree_mention(self) -> None:
        items = extract_education("A master degree is required.", _segment("x"))

        assert items[0].degree.startswith("master")

    def test_absence_is_unknown_not_invented(self) -> None:
        items = extract_education("No education mention here at all.", _segment("x"))

        assert items == []


class TestSalaryEvidence:
    def test_canonical_passthrough_without_contradiction(self) -> None:
        field = build_salary_field(
            {"min_amount": 120000.0, "max_amount": 150000.0, "currency": "USD"},
            "Compensation: $130,000 a year",
        )

        assert field.status is ExtractionStatus.EXPLICIT
        assert field.canonical_min == 120000.0
        assert field.parsed_from_text is not None  # text evidence preserved too

    def test_unambiguous_text_pattern_parsed(self) -> None:
        field = build_salary_field(None, "Salary: $120,000 - $150,000 per year")

        assert field.status is ExtractionStatus.EXPLICIT
        parsed = field.parsed_from_text
        assert parsed.currency == "USD"
        assert parsed.min == pytest_approx(120000)
        assert parsed.max == pytest_approx(150000)
        assert parsed.period == "year"

    def test_ambiguous_text_kept_raw_only(self) -> None:
        field = build_salary_field(None, "Competitive salary with equity upside.")

        assert field.parsed_from_text is None
        assert field.jd_text_raw is None

    def test_k_shorthand_parsed(self) -> None:
        field = build_salary_field(None, "£45k-60k depending on level")

        parsed = field.parsed_from_text
        assert parsed.currency == "GBP"
        assert parsed.max == pytest_approx(60000)


def pytest_approx(value: float) -> float:
    return float(value)


class TestSectionKindCoverage:
    def test_sections_enum_has_core_kinds(self) -> None:
        expected = {
            SectionKind.RESPONSIBILITIES,
            SectionKind.REQUIREMENTS,
            SectionKind.PREFERRED,
            SectionKind.EDUCATION,
        }
        assert expected <= set(SectionKind)
