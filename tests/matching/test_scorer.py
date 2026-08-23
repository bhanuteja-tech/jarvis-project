"""Scoring components: weights, neutrals, tiers, confidence."""

from __future__ import annotations

from app.matching.scorer import score_pair
from app.matching.views import build_candidate_view, build_job_view

ANALYZED = {
    "status": "ANALYZED",
    "job_index": 0,
    "analysis": {
        "skills": {
            "status": "explicit",
            "required": [{"name": "python", "requirement": "required"}],
            "preferred": [{"name": "docker", "requirement": "preferred"}],
        },
        "experience": {"min_years": 3, "max_years": 8, "level_word": None, "status": "explicit"},
        "education": {"status": "unknown", "items": []},
        "employment_type": {"value": "Full-time", "status": "explicit"},
        "work_arrangement": {"mode": "remote", "status": "explicit"},
        "location": {"job_location": "Remote", "remote_eligibility": True},
        "salary": {
            "status": "explicit",
            "canonical_min": 100000.0,
            "canonical_max": 130000.0,
            "canonical_currency": "USD",
            "parsed_from_text": None,
        },
    },
}


def score(job=None, candidate=None, analysis=ANALYZED):
    job_view = build_job_view(job or make_job(), 0, analysis)
    candidate_view = build_candidate_view(candidate or make_candidate_result())
    return score_pair(candidate_view, job_view)


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


def make_candidate_result(**profile_overrides):
    profile = {
        "skills": {
            "status": "explicit",
            "items": [
                {"name": "python", "matched_as": "Python", "category": "language"},
            ],
        },
        "experience": {
            "status": "explicit",
            "total_years": 6.0,
            "items": [
                {
                    "title": "Senior Backend Engineer",
                    "company": "Acme",
                    "location": None,
                    "start_raw": "Jan 2020",
                    "end_raw": "Present",
                    "start_iso": "2020-01-01",
                    "end_iso": None,
                    "is_current": True,
                    "duration_months": 80,
                    "highlights": ["Built services"],
                    "skills_in_role": [],
                    "evidence": {},
                },
            ],
        },
        "education": {
            "status": "explicit",
            "items": [
                {"degree": "bachelor", "degree_raw": "BSc", "field_of_study": "Computer Science"},
            ],
        },
        "projects": {
            "status": "explicit",
            "items": [
                {
                    "name": "Side Project",
                    "description": None,
                    "url": None,
                    "technologies": [
                        {"name": "fastapi", "matched_as": "FastAPI", "category": "framework"}
                    ],
                },
            ],
        },
        "preferences": {
            "status": "explicit",
            "locations": ["berlin"],
            "remote": True,
            "relocation": True,
            "employment_types": ["full_time"],
            "salary_min": {"amount": 90000.0, "currency": "USD", "period": "year"},
        },
    }
    profile.update(profile_overrides)
    return {"status": "PARSED", "profile": profile}


class TestSkills:
    def test_full_required_match_scores_30(self) -> None:
        result = score()

        assert result["breakdown"]["skills_required"].points == 30
        assert result["breakdown"]["skills_required"].status == "matched"

    def test_partial_required_fraction(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "skills": {
                    "required": [
                        {"name": "python"},
                        {"name": "pytorch"},
                        {"name": "sql"},
                    ],
                },
            },
        }
        result = score(analysis=analysis)

        component = result["breakdown"]["skills_required"]
        assert component.points == 10.0  # 30 * 1/3
        assert component.status == "partial"

    def test_preferred_contributes(self) -> None:
        result = score(candidate=make_candidate_result(
            skills={"status": "explicit", "items": [
                {"name": "python", "matched_as": "Python",
                 "category": "language"},
                {"name": "docker", "matched_as": "Docker",
                 "category": "tool"},
            ]},
        ))

        assert result["breakdown"]["skills_preferred"].points == 10

    def test_no_skills_stated_not_requested(self) -> None:
        analysis = {"status": "ANALYZED", "analysis": {"skills": {}}}
        result = score(analysis=analysis)

        assert result["breakdown"]["skills_required"].points == 30
        assert result["breakdown"]["skills_required"].status == "not_requested"


class TestExperience:
    def test_within_range_full_points(self) -> None:
        result = score()

        assert result["breakdown"]["experience"].points == 20

    def test_below_minimum_scaled_floor(self) -> None:
        candidate = make_candidate_result(
            experience={"status": "explicit", "total_years": 1.0, "items": []}
        )
        result = score(candidate=candidate)

        # floor(20 * 1 / 3) = 6
        assert result["breakdown"]["experience"].points == 6
        assert "insufficient" in result["breakdown"]["experience"].reason

    def test_above_maximum_full_with_warning_path_reason(self) -> None:
        candidate = make_candidate_result(
            experience={"status": "explicit", "total_years": 15.0, "items": []}
        )
        result = score(candidate=candidate)

        assert result["breakdown"]["experience"].points == 20
        assert "exceeds stated range" in result["breakdown"]["experience"].reason

    def test_level_word_floor_when_numeric_absent(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "experience": {"min_years": None, "max_years": None, "level_word": "senior-level"},
            },
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["experience"].points == 20

    def test_unknown_years_neutral(self) -> None:
        candidate = make_candidate_result(
            experience={"status": "unknown", "total_years": None, "items": []}
        )
        result = score(candidate=candidate)

        component = result["breakdown"]["experience"]
        assert component.points == 10
        assert component.status == "neutral"


class TestLocationRemote:
    def test_remote_job_remote_candidate_matched(self) -> None:
        result = score()

        assert result["breakdown"]["location"].points == 12

    def test_remote_job_explicit_onsite_preference_mismatch(self) -> None:
        candidate = make_candidate_result(
            preferences={
                "remote": False,
                "relocation": False,
                "locations": ["Berlin"],
                "employment_types": [],
            }
        )
        result = score(candidate=candidate)

        assert result["breakdown"]["location"].points == 0

    def test_onsite_city_mismatch_zero(self) -> None:
        job = make_job(location="New York")
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "work_arrangement": {"mode": "onsite"},
                "location": {"job_location": "New York",
                             "remote_eligibility": False},
            },
        }
        candidate = make_candidate_result(
            preferences={
                "remote": False, "relocation": False,
                "locations": ["Berlin"], "employment_types": [],
            }
        )
        result = score(job=job, analysis=analysis, candidate=candidate)

        assert result["breakdown"]["location"].points == 0

    def test_relocation_softens_city_mismatch(self) -> None:
        job = make_job(location="New York")
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "work_arrangement": {"mode": "onsite"},
                "location": {"job_location": "New York",
                             "remote_eligibility": False},
            },
        }
        candidate = make_candidate_result(
            preferences={
                "remote": None,
                "relocation": True,
                "locations": [],
                "employment_types": [],
            }
        )
        result = score(job=job, analysis=analysis, candidate=candidate)

        assert result["breakdown"]["location"].points == 9


class TestEmploymentType:
    def test_known_mismatch_zero(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {"employment_type": {"value": "Contract"}},
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["employment_type"].points == 0

    def test_job_type_unknown_neutral(self) -> None:
        job = make_job(employment_type=None)
        analysis = {"status": "ANALYZED", "analysis": {}}
        result = score(job=job, analysis=analysis)

        component = result["breakdown"]["employment_type"]
        assert component.points == 5
        assert component.status == "neutral"


class TestEducationLadder:
    def test_meets_requirement(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {"education": {"items": [{"degree": "bachelor"}]}},
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["education"].points == 8

    def test_one_level_below_partial(self) -> None:
        candidate = make_candidate_result(
            education={
                "status": "explicit",
                "items": [{"degree": "associate", "degree_raw": "Associate"}],
            }
        )
        analysis = {
            "status": "ANALYZED",
            "analysis": {"education": {"items": [{"degree": "bachelor"}]}},
        }
        result = score(candidate=candidate, analysis=analysis)

        assert result["breakdown"]["education"].points == 3.2

    def test_two_levels_below_zero(self) -> None:
        candidate = make_candidate_result(
            education={
                "status": "explicit",
                "items": [{"degree": "diploma", "degree_raw": "Diploma"}],
            }
        )
        analysis = {
            "status": "ANALYZED",
            "analysis": {"education": {"items": [{"degree": "phd"}]}},
        }
        result = score(candidate=candidate, analysis=analysis)

        assert result["breakdown"]["education"].points == 0


class TestSalary:
    def test_meets_minimum_full(self) -> None:
        result = score()

        assert result["breakdown"]["salary"].points == 5

    def test_overlap_partial(self) -> None:
        """When even the offered maximum falls short of the expected minimum,
        the entire range is below expectations => mismatch."""
        analysis = {
            "status": "ANALYZED",
            "analysis": {"salary": {
                "canonical_min": 60000.0, "canonical_max": 80000.0}},
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["salary"].points == 0
        assert "below expected minimum" in result["breakdown"]["salary"].reason

    def test_below_expectation_zero(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {"salary": {"canonical_min": 40000.0, "canonical_max": 60000.0}},
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["salary"].points == 0

    def test_currency_mismatch_zero_even_if_high(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "salary": {
                    "canonical_min": 500000.0,
                    "canonical_max": 800000.0,
                    "canonical_currency": "INR",
                }
            },
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["salary"].points == 0

    def test_missing_salary_neutral(self) -> None:
        analysis = {"status": "ANALYZED", "analysis": {"salary": {}}}
        result = score(analysis=analysis)

        component = result["breakdown"]["salary"]
        assert component.points == 2.5
        assert component.status == "neutral"


class TestLevelComponent:
    def test_equal_seniority_matched(self) -> None:
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "experience": {"min_years": None, "max_years": None, "level_word": "senior-level"},
            },
        }
        result = score(analysis=analysis)

        assert result["breakdown"]["level"].points == 5

    def test_adjacent_partial(self) -> None:
        candidate = make_candidate_result(
            experience={
                "status": "explicit",
                "total_years": 6.0,
                "items": [{"title": "Lead Engineer", "company": "Acme"}],
            }
        )
        analysis = {
            "status": "ANALYZED",
            "analysis": {
                "experience": {"min_years": None, "max_years": None, "level_word": "senior-level"},
            },
        }
        result = score(candidate=candidate, analysis=analysis)

        assert result["breakdown"]["level"].points == 3


class TestTiersAndConfidence:
    def test_tier_thresholds(self) -> None:
        from app.matching.models import tier_for

        assert tier_for(80) == "strong"
        assert tier_for(60) == "moderate"
        assert tier_for(30) == "weak"

    def test_confidence_low_when_jd_analysis_missing(self) -> None:
        result = score(analysis=None)

        assert result["confidence"] in {"low", "medium"}
