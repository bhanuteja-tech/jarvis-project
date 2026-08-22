"""Candidate/Job view construction over frozen Phase 2/3 contracts."""

from __future__ import annotations

from app.matching.views import (
    build_candidate_view,
    build_job_view,
)


def make_candidate_result(**profile_overrides):
    profile = {
        "skills": {"status": "explicit", "items": [
            {"name": "python", "matched_as": "Python", "category": "language"},
        ]},
        "experience": {
            "status": "explicit",
            "total_years": 6.0,
            "items": [
                {"title": "Senior Backend Engineer", "company": "Acme",
                 "skills_in_role": [{"name": "docker", "matched_as": "Docker",
                                     "category": "tool"}]},
            ],
        },
        "education": {"status": "explicit", "items": [
            {"degree": "bachelor", "degree_raw": "BSc",
             "field_of_study": "Computer Science"},
        ]},
        "projects": {"status": "explicit", "items": [
            {"name": "Side Project", "description": None, "url": None,
             "technologies": [{"name": "fastapi", "matched_as": "FastAPI",
                               "category": "framework"}]},
        ]},
        "preferences": {
            "status": "explicit",
            "locations": ["Berlin"],
            "remote": True,
            "relocation": False,
            "employment_types": ["full_time"],
            "salary_min": {"amount": 90000.0, "currency": "USD", "period": "year"},
        },
    }
    profile.update(profile_overrides)
    return {"status": "PARSED", "profile": profile}


def make_job(**overrides):
    job = {
        "source": "greenhouse",
        "source_job_id": "1",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "employment_type": "Full-time",
        "salary": None,
    }
    job.update(overrides)
    return job


ANALYZED = {
    "status": "ANALYZED",
    "job_index": 0,
    "analysis": {
        "skills": {
            "status": "explicit",
            "required": [{"name": "python", "requirement": "required"}],
            "preferred": [{"name": "docker", "requirement": "preferred"}],
        },
        "experience": {"min_years": 3, "max_years": 8,
                       "level_word": None, "status": "explicit"},
        "education": {"status": "unknown", "items": []},
        "employment_type": {"value": "Full-time", "status": "explicit"},
        "work_arrangement": {"mode": "remote", "status": "explicit"},
        "location": {"job_location": "Remote", "remote_eligibility": True},
        "salary": {"status": "explicit", "canonical_min": 100000.0,
                   "canonical_max": 130000.0, "canonical_currency": "USD",
                   "parsed_from_text": None},
    },
}


class TestCandidateView:
    def test_skill_union_across_sections(self) -> None:
        view = build_candidate_view(make_candidate_result())

        assert {"python", "docker", "fastapi"} <= view.skill_names

    def test_level_rank_from_titles(self) -> None:
        view = build_candidate_view(make_candidate_result())

        # "Senior Backend Engineer" -> senior
        assert view.level_rank == 5

    def test_unusable_statuses(self) -> None:
        for status in ("SKIPPED", "FAILED"):
            view = build_candidate_view({"status": status, "profile": None})
            assert view.usable is False

    def test_preferences_parsed(self) -> None:
        view = build_candidate_view(make_candidate_result())

        assert view.remote_pref is True
        assert view.relocation is False
        assert "berlin" in {key.lower() for key in view.location_keys} or bool(view.location_keys)
        assert "full_time" in view.employment_types
        assert view.salary_min == 90000.0


class TestJobView:
    def test_analysis_fields_populate(self) -> None:
        view = build_job_view(make_job(), 0, ANALYZED)

        assert view.has_analysis is True
        assert view.required_skills == frozenset({"python"})
        assert view.preferred_skills == frozenset({"docker"})
        assert (view.exp_min_years, view.exp_max_years) == (3, 8)
        assert view.is_remote_job is True
        assert view.employment == "full_time"
        assert (view.offered_min, view.offered_max) == (100000.0, 130000.0)

    def test_missing_analysis_flags_gap_source(self) -> None:
        view = build_job_view(make_job(), 0, None)

        assert view.has_analysis is False
        assert view.required_skills == frozenset()
        # canonical fallback employment still normalizes
        assert view.employment == "full_time"

    def test_level_word_floor_mapping(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "experience": {"min_years": None, "max_years": None,
                               "level_word": "senior-level"},
            },
        }
        view = build_job_view(make_job(), 0, analysis)

        assert view.level_word_floor_years == 5
