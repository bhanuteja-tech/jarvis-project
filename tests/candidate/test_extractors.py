"""Candidate extractors: contact/PII, identity, dates, education,
certifications, projects, preferences."""

from __future__ import annotations

from datetime import UTC, datetime

from app.candidate.extractors import (
    extract_certification_items,
    extract_contact,
    extract_education_items,
    extract_experience_field,
    extract_identity,
    extract_preferences,
    extract_project_items,
    parse_date_token,
)
from app.candidate.text_sections import build_document, segment_resume

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


class TestContactQuarantine:
    def test_email_phone_link_extracted(self) -> None:
        text = (
            "Jane Doe\njane.doe@example.com | +1 415 555 0100\n"
            "https://www.linkedin.com/in/janedoe\nhttps://github.com/janedoe\n"
        )

        emails, phones, links, evidence = extract_contact(text)

        assert emails == ["jane.doe@example.com"]
        assert len(phones) == 1
        labels = {link.label for link in links}
        assert {"linkedin", "github"} <= labels
        assert evidence

    def test_phone_regex_does_not_capture_years(self) -> None:
        _emails, phones, _links, _ev = extract_contact("Engineer since Jan 2020 with 2024 project")
        assert phones == []


class TestIdentityHeuristic:
    def test_first_clean_line_becomes_name(self) -> None:
        name, evidence = extract_identity(["Jane Doe", "jane@example.com", "Senior Engineer"])

        assert name == "Jane Doe"
        assert evidence is not None

    def test_contact_lines_are_not_names(self) -> None:
        name, _evidence = extract_identity(
            ["jane@example.com", "https://github.com/jane", "Jane Doe"]
        )

        assert name == "Jane Doe"


class TestDateParsing:
    def test_month_year_form(self) -> None:
        iso, is_current = parse_date_token("Jan 2020")

        assert iso == "2020-01-01"
        assert is_current is False

    def test_year_only_form_defaults_to_january(self) -> None:
        iso, _ = parse_date_token("2019")

        assert iso == "2019-01-01"

    def test_present_token(self) -> None:
        iso, is_current = parse_date_token("Present")

        assert iso is None
        assert is_current is True


class TestExperienceExtraction:
    RESUME = (
        "Professional Experience\n"
        "Senior Platform Engineer - Acme Corp\n"
        "Jan 2020 - Present\n"
        "- Shipped the core platform.\n"
        "Software Engineer at Beta LLC\n"
        "Jun 2017 - Dec 2019\n"
        "- Built services.\n"
    )

    def test_entries_dates_and_durations(self) -> None:
        document = build_document(self.RESUME, max_chars=30_000)
        segmentation = segment_resume(document)

        field = extract_experience_field(segmentation, now=NOW)

        assert field.status.value == "explicit"
        assert len(field.items) == 2
        first, second = field.items
        assert first.title == "Senior Platform Engineer"
        assert first.company == "Acme Corp"
        assert first.is_current is True
        # Jan 2020 .. Aug 2026 (injected now) inclusive months.
        assert first.duration_months == (2026 - 2020) * 12 + (8 - 1) + 1
        assert second.duration_months == 31  # Jun 2017..Dec 2019 inclusive
        # All entries parsed => total years present.
        assert field.total_years is not None and field.total_years > 5

    def test_total_years_none_below_coverage_threshold(self) -> None:
        resume = (
            "Professional Experience\n"
            "Engineer at Acme\nJan 2020 - Mar 2021\n"
            "- Worked.\n"
            "Consulting adventure without dates\n"
            "- Also worked.\n"
        )
        document = build_document(resume, max_chars=30_000)
        segmentation = segment_resume(document)

        field = extract_experience_field(segmentation, now=NOW)

        assert len(field.items) == 2
        assert field.total_years is None  # 1/2 parseable < 80% threshold


class TestEducationExtraction:
    def test_full_degree_line(self) -> None:
        items = extract_education_items(None, "BSc in Computer Science, Acme University, 2015")

        assert items[0].degree == "bachelor"
        assert items[0].field_of_study.lower().startswith("computer science")
        assert items[0].institution == "Acme University"
        assert items[0].graduation_year == 2015

    def test_bootcamp_recognized(self) -> None:
        items = extract_education_items(None, "Full-stack Bootcamp, 2021")

        assert items[0].degree == "bootcamp"

    def test_no_education_is_empty_list(self) -> None:
        assert extract_education_items(None, "No academics here.") == []


class TestCertifications:
    def test_lexicon_hits_and_display_dedup(self) -> None:
        items = extract_certification_items(
            "AWS Certified Solutions Architect; CKA; PMP certified."
        )

        names = {item.name for item in items}
        assert "AWS Certified Solutions Architect" in names
        assert any("Kubernetes" in name for name in names)
        # CKA and its long-form display collapse to one entry.
        assert sum(1 for n in names if "Kubernetes" in n) == 1


class TestProjects:
    def test_project_fields(self) -> None:
        raw = (
            "Projects\n"
            "Jarvis Pipeline\n- Built https://github.com/me/jarvis using python "
            "and fastapi for resume parsing.\n"
        )
        segmentation = segment_resume(build_document(raw, max_chars=30_000))

        items = extract_project_items(segmentation)

        assert items[0].name == "Jarvis Pipeline"
        assert items[0].url == "https://github.com/me/jarvis"
        tech = {skill.name for skill in items[0].technologies}
        assert {"python", "fastapi"} <= tech


class TestPreferences:
    def test_explicit_statements_only(self) -> None:
        info = extract_preferences(
            "Open to remote. Seeking full-time roles. Willing to relocate. "
            "Preferred locations: Berlin, Amsterdam. Expected salary: ₹2,500,000"
        )

        assert info.remote is True
        assert info.relocation is True
        assert info.employment_types == ["full_time"]
        assert [loc.lower() for loc in info.locations] == ["berlin", "amsterdam"]
        assert info.salary_min is not None
        assert info.salary_min.currency == "INR"
        assert info.status.value == "explicit"

    def test_never_inferred_from_history(self) -> None:
        info = extract_preferences("Worked remotely at Acme 2019-2021 on full-time contracts.")

        assert info.remote is None
        assert info.relocation is None
        assert info.employment_types == []
