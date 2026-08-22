"""ResumeAnalyzer envelopes: SKIPPED/FAILED/PARSED/PARTIAL, structured
input, redaction, deterministic Present handling."""

from __future__ import annotations

from datetime import UTC, datetime

from app.candidate.analyzer import ResumeAnalyzer
from app.config.settings import Settings

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)

GOOD_RESUME = """Jane Doe
jane.doe@example.com | +1 415 555 0100
https://github.com/janedoe

Summary
Platform engineer focused on python and kubernetes.

Skills
Python, Kubernetes, PostgreSQL

Professional Experience
Senior Platform Engineer - Acme Corp
Jan 2020 - Present
- Shipped the core platform.
Software Engineer at Beta LLC
Jun 2017 - Dec 2019
- Built services.

Education
BSc in Computer Science, Acme University, 2015

Certifications
AWS Certified Solutions Architect

Projects
Resume Parser
- Built with python; https://github.com/janedoe/parser
"""


def make_analyzer(**overrides) -> ResumeAnalyzer:
    values = {
        "candidate_max_chars": 30_000,
        "candidate_redact_pii": False,
    }
    values.update(overrides)
    return ResumeAnalyzer(Settings(**values), now=NOW)


class TestEnvelopes:
    async def test_absent_input_skipped_silently(self) -> None:
        result = await make_analyzer().build_profile(None)

        assert result.status == "SKIPPED"
        assert result.profile is None
        assert result.reason == "no_input"

    async def test_empty_text_fails_with_reason(self) -> None:
        result = await make_analyzer().build_profile({"text": "   "})

        assert result.status == "FAILED"
        assert result.reason == "empty_resume"

    async def test_oversized_text_fails_hard_no_truncation(self) -> None:
        analyzer = make_analyzer(candidate_max_chars=500)

        result = await analyzer.build_profile({"text": "word " * 400})

        assert result.status == "FAILED"
        assert result.reason == "max_chars_violation"
        assert result.profile is None

    async def test_invalid_input_shape(self) -> None:
        result = await make_analyzer().build_profile({"foo": "bar"})

        assert result.status == "FAILED"
        assert result.reason == "invalid_candidate_input"


class TestFullParse:
    async def test_good_resume_parsed_with_provenance(self) -> None:
        result = await make_analyzer().build_profile({"text": GOOD_RESUME})

        assert result.status in {"PARSED", "PARTIAL"}
        profile = result.profile
        assert profile is not None
        assert profile.source_format.value == "plain_text"

        # PII quarantined but present (redaction off by default).
        assert profile.contact.pii is True
        assert profile.contact.emails == ["jane.doe@example.com"]
        assert profile.identity.status.value == "inferred"
        assert profile.identity.full_name == "Jane Doe"

        skills = {skill.name for skill in profile.skills.items}
        assert {"python", "kubernetes", "postgresql"} <= skills

        assert len(profile.experience.items) == 2
        current = profile.experience.items[0]
        assert current.is_current is True
        assert current.end_iso == "2026-08-01"  # injected NOW month, not hidden clock drift
        assert profile.experience.total_years is not None

        assert profile.education.items[0].degree == "bachelor"
        names = {cert.name for cert in profile.certifications.items}
        assert any("Solutions Architect" in name for name in names)
        assert profile.projects.items[0].name == "Resume Parser"

        assert {"summary", "skills", "experience", "education"} <= set(
            profile.coverage.sections_found
        )

    async def test_sparse_resume_is_partial_not_failed(self) -> None:
        result = await make_analyzer().build_profile(
            {"text": "Just a person who likes technology."}
        )

        assert result.status == "PARTIAL"
        profile = result.profile
        assert profile.skills.status.value == "unknown"
        assert profile.experience.status.value == "unknown"


class TestStructuredInput:
    async def test_structured_passthrough_validated(self) -> None:
        payload = {
            "identity": {
                "status": "explicit",
                "full_name": "Alex Chen",
            },
            "skills": {
                "status": "explicit",
                "items": [
                    {
                        "name": "python",
                        "matched_as": "Python",
                        "category": "language",
                    }
                ],
            },
        }

        result = await make_analyzer().build_profile({"structured": payload})

        assert result.status == "PARSED"
        profile = result.profile
        assert profile.source_format.value == "structured"
        assert profile.identity.full_name == "Alex Chen"
        assert {skill.name for skill in profile.skills.items} == {"python"}

    async def test_invalid_structured_fails_typed(self) -> None:
        result = await make_analyzer().build_profile(
            {"structured": {"skills": {"status": "explicit", "items": "not-a-list"}}}
        )

        assert result.status == "FAILED"
        assert result.reason == "invalid_structured_input"


class TestRedaction:
    async def test_redact_flag_strips_pii_preserves_fact(self) -> None:
        analyzer = make_analyzer(candidate_redact_pii=True)

        result = await analyzer.build_profile({"text": GOOD_RESUME})

        profile = result.profile
        assert profile.redacted is True
        assert profile.contact.emails == []
        assert profile.contact.phones == []
        assert profile.contact.pii is True  # block remains, marked PII
