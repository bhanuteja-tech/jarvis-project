"""Tailoring service: envelope statuses, evidence refs, PII exclusion,
LLM-disabled default, deterministic output."""

from __future__ import annotations

import asyncio

from app.config.settings import Settings
from app.tailoring.service import tailor_resume

RESUME_PROFILE = {
    "status": "PARSED",
    "profile": {
        "profile_id": "pid-1",
        "skills": {
            "status": "explicit",
            "items": [
                {"name": "python", "matched_as": "Python", "category": "language"},
                {"name": "sql", "matched_as": "SQL", "category": "language"},
            ],
        },
        "experience": {
            "status": "explicit",
            "total_years": 6.0,
            "items": [
                {
                    "title": "Data Engineer",
                    "company": "Acme",
                    "start_raw": "Jan 2021",
                    "end_raw": "Present",
                    "start_iso": "2021-01-01",
                    "end_iso": "2026-08-01",
                    "is_current": True,
                    "duration_months": 68,
                    "highlights": [
                        "Built python data pipelines",
                        "Managed postgres cluster",
                        "Answered support tickets",
                    ],
                    "skills_in_role": [],
                },
            ],
        },
        "projects": {
            "status": "explicit",
            "items": [
                {
                    "name": "ETL Tool",
                    "description": "python etl toolkit",
                    "url": None,
                    "technologies": [{"name": "python", "matched_as": "Python"}],
                },
            ],
        },
        "education": {
            "status": "explicit",
            "items": [
                {
                    "degree": "bachelor",
                    "degree_raw": "BSc",
                    "field_of_study": "Computer Science",
                    "institution": "Acme University",
                    "graduation_year": 2018,
                },
            ],
        },
        "certifications": {
            "status": "explicit",
            "items": [{"name": "AWS Certified Solutions Architect"}],
        },
        "summary": {"status": "explicit", "text": "Data engineer with python focus."},
        "preferences": {
            "status": "unknown",
            "locations": [],
            "remote": None,
            "relocation": None,
            "employment_types": [],
            "salary_min": None,
            "evidence": [],
        },
    },
}

MATCH = {
    "job_index": 0,
    "score": 78.0,
    "tier": "strong",
    "matched_skills": ["python"],
    "missing_required": ["docker"],
}

ANALYSIS = {
    "status": "ANALYZED",
    "job_index": 0,
    "analysis": {
        "skills": {
            "required": [{"name": "python"}, {"name": "docker"}],
            "preferred": [{"name": "sql"}],
        },
        "responsibilities": {
            "items": [
                {"text": "Build python data pipelines"},
            ]
        },
    },
}

JOBS = [
    {"source": "greenhouse", "source_job_id": "1", "title": "Data Engineer", "company": "TargetCo"}
]


def run(**settings_overrides):
    settings = Settings(
        tailor_max_highlights=3,
        tailor_max_projects=3,
        tailoring_llm_enabled=False,
        **settings_overrides,
    )
    return asyncio.run(
        tailor_resume(
            RESUME_PROFILE,
            [MATCH],
            [ANALYSIS],
            JOBS,
            None,
            settings,
        )
    )


class TestHappyPath:
    def test_tailored_with_evidence_refs(self) -> None:
        outcome = run()

        result = outcome.result
        assert result.status.value == "tailored"
        resume = result.resume
        assert resume is not None

        assert resume.target_job_index == 0
        assert resume.target_job_title == "Data Engineer"
        assert resume.source_profile_id == "pid-1"

        # JD-required matched first; missing required NEVER inserted.
        assert resume.skills[0].name == "python"
        assert resume.skills[0].requirement == "required"
        skill_names = {skill.name for skill in resume.skills}
        assert "docker" not in skill_names
        assert resume.unaddressed_jd_requirements == ["docker"]

        # Highlight selection kept the relevant bullet and dropped the rest.
        exp_item = resume.experience[0]
        assert exp_item.source_index == 0
        kept_texts = [bullet.final_text for bullet in exp_item.highlights]
        assert kept_texts == ["Built python data pipelines"]

        # Every bullet keeps its original text alongside (truth diff).
        assert all(
            bullet.final_text.startswith(bullet.original_text.split()[0])
            or bullet.final_text == bullet.original_text
            for item in resume.experience
            for bullet in item.highlights
        )

        # PII never copied.
        dumped = resume.model_dump_json()
        assert "jane" not in dumped.lower()
        assert "@" not in dumped

        # Change records exist for the applied operations.
        operations = {change.operation for change in resume.changes}
        assert {"skill_priority", "highlight_select", "summary_generate"} <= operations

    def test_deterministic_repeat_runs(self) -> None:
        first = run().result.model_dump()
        second = run().result.model_dump()

        # duration_ms differs by design; strip metadata before comparing.
        first["resume"]["metadata"]["duration_ms"] = None
        second["resume"]["metadata"]["duration_ms"] = None
        assert first == second


class TestDegradedPaths:
    def test_missing_jd_analysis_is_partial(self) -> None:
        outcome = asyncio.run(tailor_resume(
            RESUME_PROFILE,
            [MATCH],
            [],
            JOBS,
            None,
            Settings(tailor_max_highlights=3, tailor_max_projects=3),
        ))

        result = outcome.result
        assert result.status.value == "partial"
        assert any(
            "jd analysis unavailable" in change.reason.lower() for change in result.resume.changes
        )

    def test_no_matches_fails(self) -> None:
        outcome = asyncio.run(tailor_resume(
            RESUME_PROFILE,
            [],
            [],
            JOBS,
            None,
            Settings(),
        ))

        assert outcome.result.status.value == "failed"
        assert outcome.result.reason == "no_matches"

    def test_invalid_override_target_fails(self) -> None:
        outcome = asyncio.run(tailor_resume(
            RESUME_PROFILE,
            [MATCH],
            [ANALYSIS],
            JOBS,
            {"target_job_index": 42},
            Settings(),
        ))

        assert outcome.result.status.value == "failed"
        assert outcome.result.reason == "invalid_target_job_index"

    def test_unusable_candidate_skips(self) -> None:
        outcome = asyncio.run(tailor_resume(
            {"status": "FAILED", "profile": None},
            [MATCH],
            [ANALYSIS],
            JOBS,
            None,
            Settings(),
        ))

        assert outcome.result.status.value == "skipped"
        assert outcome.result.reason == "no_usable_candidate_profile"

    def test_sparse_profile_partial_without_invention(self) -> None:
        sparse = {
            "status": "PARTIAL",
            "profile": {
                "profile_id": "pid-2",
                "skills": {"status": "unknown", "items": []},
                "experience": {"status": "unknown", "total_years": None, "items": []},
                "education": {"status": "unknown", "items": []},
                "certifications": {"status": "unknown", "items": []},
                "projects": {"status": "unknown", "items": []},
                "summary": {"status": "unknown", "text": None},
                "preferences": {"status": "unknown"},
            },
        }
        outcome = asyncio.run(tailor_resume(
            sparse,
            [MATCH],
            [ANALYSIS],
            JOBS,
            None,
            Settings(tailor_max_highlights=3, tailor_max_projects=3),
        ))

        result = outcome.result
        assert result.status.value == "partial"
        assert result.resume.skills == []
        assert result.resume.experience == []
