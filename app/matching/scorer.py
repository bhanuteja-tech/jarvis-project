"""Deterministic scoring: fixed weights, labeled neutrals, tiers.

Weights (approved, total 100):
    required skills 30 · preferred skills 10 · experience 20
    location 12 · employment type 10 · education 8 · level 5 · salary 5

No hard filters exist in Phase 4; every job is scored and tiered
(strong >= 75, moderate >= 50, weak < 50). Missing data yields labeled
neutral partials — never positive evidence.
"""

from __future__ import annotations

import math
from typing import Any

from app.matching.models import ComponentResult, tier_for
from app.matching.views import LEVEL_WORD_MIN_YEARS, CandidateView, JobView

_REQUIRED_MAX = 30.0
_PREFERRED_MAX = 10.0
_EXPERIENCE_MAX = 20.0
_LOCATION_MAX = 12.0
_EMPLOYMENT_MAX = 10.0
_EDUCATION_MAX = 8.0
_LEVEL_MAX = 5.0
_SALARY_MAX = 5.0


def score_pair(candidate: CandidateView, job_view: JobView) -> dict[str, Any]:
    breakdown = {
        "skills_required": _skills_required(candidate, job_view),
        "skills_preferred": _skills_preferred(candidate, job_view),
        "experience": _experience(candidate, job_view),
        "location": _location(candidate, job_view),
        "employment_type": _employment(candidate, job_view),
        "education": _education(candidate, job_view),
        "level": _level(candidate, job_view),
        "salary": _salary(candidate, job_view),
    }

    components = list(breakdown.values())
    total = round(sum(component.points for component in components), 2)
    fallback_count = sum(
        1 for c in components if "unavailable" in c.reason or "fallback" in c.reason
    )
    neutral_count = sum(1 for c in components if c.status == "neutral")

    if not job_view.has_analysis or fallback_count >= 2:
        confidence = "low"
    elif neutral_count or fallback_count:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "breakdown": breakdown,
        "total": total,
        "tier": tier_for(total),
        "confidence": confidence,
        "fallbacks": fallback_count,
    }


def _skills_required(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    if not job_view.required_skills:
        return ComponentResult(
            "skills_required", 30, 30, "not_requested", "JD analysis states no required skills"
        )
    matched = job_view.required_skills & candidate.skill_names
    points = round(30 * len(matched) / len(job_view.required_skills), 2)
    status = (
        "matched"
        if len(matched) == len(job_view.required_skills)
        else ("partial" if matched else "mismatch")
    )
    return ComponentResult(
        "skills_required",
        points,
        30,
        status,
        f"Matched {len(matched)} of {len(job_view.required_skills)} required skills",
    )


def _skills_preferred(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    if not job_view.preferred_skills:
        return ComponentResult(
            "skills_preferred", 10, 10, "not_requested", "JD analysis states no preferred skills"
        )
    matched = job_view.preferred_skills & candidate.skill_names
    points = round(10 * len(matched) / len(job_view.preferred_skills), 2)
    status = (
        "matched"
        if len(matched) == len(job_view.preferred_skills)
        else ("partial" if matched else "mismatch")
    )
    return ComponentResult(
        "skills_preferred",
        points,
        10,
        status,
        f"Matched {len(matched)} of {len(job_view.preferred_skills)} preferred skills",
    )


def _experience(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    required_min = job_view.exp_min_years
    required_max = job_view.exp_max_years
    if required_min is None and required_max is None:
        floor = job_view.level_word_floor_years
        if floor is None:
            return ComponentResult(
                "experience",
                10,
                20,
                "not_requested",
                "JD analysis unavailable; canonical job fallback used"
                if not job_view.has_analysis
                else "JD states no explicit experience requirement",
            )
        required_min = floor

    years = candidate.total_years
    if years is None:
        return ComponentResult(
            "experience",
            10,
            20,
            "neutral",
            "candidate experience unknown (insufficient date coverage)",
        )

    if required_min is not None and years < required_min:
        points = math.floor(20 * years / required_min) if required_min > 0 else 20.0
        return ComponentResult(
            "experience",
            float(points),
            20,
            "partial",
            f"Candidate has insufficient experience ({years:g} of at least {required_min:g} years)",
        )
    if required_max is not None and years > required_max:
        return ComponentResult(
            "experience",
            20,
            20,
            "matched",
            f"Candidate exceeds stated range ({years:g} vs max {required_max:g})",
        )
    return ComponentResult(
        "experience",
        20,
        20,
        "matched",
        f"Candidate experience ({years:g}y) meets requirement"
        + (f" of {required_min:g}+ years" if required_min is not None else ""),
    )


def _location(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    if job_view.is_remote_job:
        # Explicit onsite-only preference is checked FIRST: it overrides
        # relocation willingness because the user explicitly said onsite.
        if candidate.remote_pref is False:
            return ComponentResult(
                "location",
                0,
                12,
                "mismatch",
                "Remote role but candidate prefers onsite",
            )
        if candidate.remote_pref is True:
            return ComponentResult("location", 12, 12, "matched", "Candidate accepts remote work")
        if candidate.relocation is True:
            return ComponentResult(
                "location",
                12,
                12,
                "matched",
                "Remote role; relocation accepted anyway",
            )
        return ComponentResult(
            "location", 9, 12, "neutral", "Remote role; candidate preference unknown"
        )

    if job_view.location_key is None:
        return ComponentResult("location", 6, 12, "neutral", "Job location unknown")

    matches = bool(candidate.location_keys) and job_view.location_key in candidate.location_keys
    if matches:
        return ComponentResult(
            "location",
            12,
            12,
            "matched",
            f"Location matches candidate preference '{job_view.location_key}'",
        )
    if candidate.relocation is True:
        return ComponentResult(
            "location",
            9,
            12,
            "partial",
            "Location differs but candidate is willing to relocate",
        )
    if not candidate.location_keys:
        return ComponentResult(
            "location",
            9,
            12,
            "neutral",
            "Onsite role; candidate location preferences unknown",
        )
    return ComponentResult(
        "location",
        0,
        12,
        "mismatch",
        f"Location mismatch ('{job_view.location_key}')",
    )


def _employment(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    if not candidate.employment_types:
        return ComponentResult(
            "employment_type",
            10,
            10,
            "not_requested",
            "Candidate stated no employment-type preference",
        )
    if job_view.employment is None:
        return ComponentResult("employment_type", 5, 10, "neutral", "Job employment type unknown")
    if job_view.employment in candidate.employment_types:
        return ComponentResult(
            "employment_type",
            10,
            10,
            "matched",
            f"Employment type '{job_view.employment}' matches preference",
        )
    return ComponentResult(
        "employment_type",
        0,
        10,
        "mismatch",
        f"Employment type '{job_view.employment}' outside preference",
    )


def _education(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    required_rank = job_view.edu_required_rank
    if required_rank is None:
        return ComponentResult(
            "education", 8, 8, "not_requested", "JD states no education requirement"
        )
    candidate_rank = candidate.highest_edu_rank
    if candidate_rank is None:
        return ComponentResult("education", 4, 8, "neutral", "candidate education unknown")
    if candidate_rank >= required_rank:
        return ComponentResult(
            "education", 8, 8, "matched", "Candidate education meets requirement"
        )
    if required_rank - candidate_rank == 1:
        return ComponentResult(
            "education", 3.2, 8, "partial", "Candidate education one level below requirement"
        )
    return ComponentResult("education", 0, 8, "mismatch", "Candidate education below requirement")


def _level(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    candidate_rank = candidate.level_rank
    jd_level_rank = _jd_level_rank(job_view)
    if candidate_rank is None or jd_level_rank is None:
        return ComponentResult("level", 2.5, 5, "neutral", "seniority not detectable on one side")
    distance = abs(candidate_rank - jd_level_rank)
    if distance == 0:
        return ComponentResult("level", 5, 5, "matched", "Seniority aligns with JD")
    if distance == 1:
        return ComponentResult("level", 3, 5, "partial", "Seniority adjacent to JD expectation")
    return ComponentResult("level", 0, 5, "mismatch", "Seniority gap versus JD expectation")


#: floor-years -> lowest ladder index with that floor (deterministic map)
_FLOOR_TO_RANK: dict[int, int] = {}
for _rank_index, _level_name in enumerate(
    ("intern", "fresher", "entry", "junior", "mid", "senior", "lead", "principal")
):
    _floor_value = LEVEL_WORD_MIN_YEARS[_level_name]
    if _floor_value not in _FLOOR_TO_RANK:
        _FLOOR_TO_RANK[_floor_value] = _rank_index


def _jd_level_rank(job_view: JobView) -> int | None:
    """JD seniority rank derived from the stated level_word's year-floor."""
    floor = job_view.level_word_floor_years
    if floor is None:
        return None
    return _FLOOR_TO_RANK.get(floor)


def _salary(candidate: CandidateView, job_view: JobView) -> ComponentResult:
    """Salary compatibility.

    Full credit when offered_max >= expected_min.
    No credit when even the top of the range falls short.
    Missing data yields labeled neutrality — never positive evidence.
    """
    expected = candidate.salary_min
    if expected is None:
        return ComponentResult(
            "salary", 5, 5, "not_requested", "Candidate stated no minimum salary"
        )
    offered_low = job_view.offered_min
    offered_high = job_view.offered_max
    if offered_low is None and offered_high is None:
        return ComponentResult("salary", 2.5, 5, "neutral", "salary unavailable")
    if (
        job_view.offered_currency is not None
        and candidate.salary_currency is not None
        and job_view.offered_currency.upper() != candidate.salary_currency.upper()
    ):
        return ComponentResult(
            "salary",
            0,
            5,
            "mismatch",
            f"Currency mismatch ({job_view.offered_currency} vs {candidate.salary_currency})",
        )
    top = offered_high if offered_high is not None else offered_low
    if top is not None and top >= expected:
        return ComponentResult("salary", 5, 5, "matched", "Offered salary meets expected minimum")
    return ComponentResult(
        "salary",
        0,
        5,
        "mismatch",
        f"Offered maximum ({top:g}) below expected minimum ({expected:g})"
        if top is not None
        else "Offered salary below expected minimum",
    )


__all__ = ["score_pair"]
