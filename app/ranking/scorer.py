"""Transparent 0-100 additive scoring with per-component explanations.

Weights (justified against the product's query shape, e.g. "recent ML
engineer jobs in Bangalore, preferably internships, last 24 hours"):

    title 30 · skills 25 (required 15 + preferred 10) · location 15
    level 10 · freshness 10 · employment_type 5 · salary 5

Components the user never specified award full points with status
``not_requested`` so totals remain comparable without penalizing absence of
constraints. Missing job data yields labeled NEUTRAL partial credit — never
positive evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.dedup.normalize import base_normalize
from app.ranking.features import JobFeatures, SkillMatch, find_skill
from app.ranking.preferences import (
    ExperienceLevel,
    SearchPreferences,
    role_variants,
)

_TITLE_MAX = 30
_REQUIRED_SKILLS_MAX = 15
_PREFERRED_SKILLS_MAX = 10
_LOCATION_MAX = 15
_LEVEL_MAX = 10
_FRESHNESS_MAX = 10
_EMPLOYMENT_MAX = 5
_SALARY_MAX = 5


@dataclass(frozen=True)
class ComponentResult:
    component: str
    points: float
    max: float
    status: str          # matched | mismatch | neutral | not_requested
    reason: str


@dataclass(frozen=True)
class ScoringResult:
    total: float
    breakdown: dict[str, Any]
    matched_skills: tuple[str, ...]
    missing_required_skills: tuple[str, ...]
    tie_key: tuple


def score_job(
    features: JobFeatures,
    prefs: SearchPreferences,
    *,
    now: datetime | None = None,
) -> ScoringResult:
    soft = prefs.soft
    breakdown: dict[str, Any] = {}
    matched: list[str] = []
    missing_required: list[str] = []

    # ---- title relevance (30) -------------------------------------------
    if not soft.target_roles:
        title_component = ComponentResult(
            "title", _TITLE_MAX, _TITLE_MAX, "not_requested", "no target roles supplied"
        )
        title_points = float(_TITLE_MAX)
    else:
        best = 0.0
        reason = "unrelated to target roles"
        for role in soft.target_roles:
            variants = role_variants(role)
            if features.title_key in variants:
                best = max(best, float(_TITLE_MAX))
                reason = f"title matches requested role '{role}'"
                break
            variant_tokens = [set(v.split()) for v in variants]
            jac = max(
                (
                    len(features.title_tokens & tokens)
                    / max(1, len(features.title_tokens | tokens))
                    for tokens in variant_tokens
                ),
                default=0.0,
            )
            candidate_points = round(_TITLE_MAX * 0.8)
            if jac >= 0.8 and candidate_points > best:
                best = candidate_points
                reason = f"title closely related to '{role}'"
            elif jac >= 0.5:
                scaled = round(6 + 12 * ((jac - 0.5) / 0.5))
                if scaled > best:
                    best = float(scaled)
                    reason = f"title partially overlaps '{role}'"
        title_points = best
        title_component = ComponentResult(
            "title", title_points, _TITLE_MAX,
            "matched" if title_points > 0 else "mismatch", reason,
        )
    breakdown["title"] = title_component

    # ---- skills (25) ------------------------------------------------------
    required_matches: list[SkillMatch] = []
    preferred_matches: list[SkillMatch] = []
    if soft.required_skills:
        for skill in soft.required_skills:
            match = find_skill(features, skill)
            if match is None:
                missing_required.append(skill)
            else:
                required_matches.append(match)
                matched.append(skill)
        required_points = round(
            _REQUIRED_SKILLS_MAX * len(required_matches) / len(soft.required_skills), 2
        )
        required_status = (
            "matched" if required_points == _REQUIRED_SKILLS_MAX
            else "partial" if required_matches else "missing"
        )
    else:
        required_points = float(_REQUIRED_SKILLS_MAX)
        required_status = "not_requested"

    if soft.preferred_skills:
        for skill in soft.preferred_skills:
            match = find_skill(features, skill)
            if match is not None:
                preferred_matches.append(match)
                if skill not in matched:
                    matched.append(skill)
        preferred_points = round(
            _PREFERRED_SKILLS_MAX * len(preferred_matches) / len(soft.preferred_skills), 2
        )
        preferred_status = "matched" if preferred_matches else "missing"
    else:
        preferred_points = float(_PREFERRED_SKILLS_MAX)
        preferred_status = "not_requested"

    breakdown["skills"] = {
        "required": ComponentResult(
            "skills.required",
            required_points,
            _REQUIRED_SKILLS_MAX,
            required_status,
            (
                f"{len(required_matches)}/{len(soft.required_skills)} required skills matched"
                if soft.required_skills else "no required skills supplied"
            ),
        ),
        "preferred": ComponentResult(
            "skills.preferred",
            preferred_points,
            _PREFERRED_SKILLS_MAX,
            preferred_status,
            (
                f"{len(preferred_matches)}/{len(soft.preferred_skills)} preferred skills matched"
                if soft.preferred_skills else "no preferred skills supplied"
            ),
        ),
    }

    # ---- location (15) ----------------------------------------------------
    if not hard_locations(prefs):
        location_component = ComponentResult(
            "location", _LOCATION_MAX, _LOCATION_MAX,
            "not_requested", "no location requirement supplied",
        )
    elif not features.location_known:
        location_points = 7.0
        location_component = ComponentResult(
            "location", location_points, _LOCATION_MAX,
            "neutral", "job location unknown",
        )
    else:
        requested_keys = {
            base_normalize(location) for location in prefs.hard.locations
        }
        job_key = base_normalize(features.location_key or "")
        remote_requested = any("remote" in key for key in requested_keys)
        job_remote = features.location_key == "remote" or features.is_remote is True
        if job_key in requested_keys or (remote_requested and job_remote):
            location_points = float(_LOCATION_MAX)
            location_component = ComponentResult(
                "location", location_points, _LOCATION_MAX,
                "matched", "location matches requirement",
            )
        else:
            location_component = ComponentResult(
                "location", 0.0, _LOCATION_MAX,
                "mismatch",
                f"job location '{features.location_key}' differs from request",
            )
    breakdown["location"] = location_component

    # ---- experience / level (10) -------------------------------------------
    if not prefs.hard.experience_levels and not soft.prefer_internship_fresher:
        level_component = ComponentResult(
            "experience", _LEVEL_MAX, _LEVEL_MAX,
            "not_requested", "no level preference supplied",
        )
    elif features.level is None:
        level_component = ComponentResult(
            "experience", _LEVEL_MAX * 0.5, _LEVEL_MAX,
            "neutral", "level not detectable from verified fields",
        )
    elif features.level in prefs.hard.experience_levels:
        level_component = ComponentResult(
            "experience", float(_LEVEL_MAX), _LEVEL_MAX,
            "matched", f"detected level {features.level.value}",
        )
    elif soft.prefer_internship_fresher and features.level in {
        ExperienceLevel.INTERN, ExperienceLevel.FRESHER
    }:
        level_component = ComponentResult(
            "experience", float(_LEVEL_MAX), _LEVEL_MAX,
            "matched", "intern/fresher preference satisfied",
        )
    else:
        level_component = ComponentResult(
            "experience", 0.0, _LEVEL_MAX,
            "mismatch", f"detected level {features.level.value} outside preference",
        )
    breakdown["experience"] = level_component

    # ---- freshness (10) -----------------------------------------------------
    reference = now or datetime.now().astimezone()
    if features.created_at is None:
        freshness_component = ComponentResult(
            "freshness", 3.0, _FRESHNESS_MAX,
            "neutral", "posting date unavailable from source",
        )
    else:
        age_hours = max(0.0, (reference - features.created_at).total_seconds() / 3600.0)
        if age_hours <= 24:
            points, tier = 10.0, "<=24h"
        elif age_hours <= 72:
            points, tier = 8.0, "<=3d"
        elif age_hours <= 24 * 7:
            points, tier = 6.0, "<=7d"
        elif age_hours <= 24 * 14:
            points, tier = 4.0, "<=14d"
        elif age_hours <= 24 * 30:
            points, tier = 2.0, "<=30d"
        else:
            points, tier = 1.0, ">30d"
        freshness_component = ComponentResult(
            "freshness", points, _FRESHNESS_MAX,
            "matched" if points >= 6 else "weak",
            f"posted {tier} ago (source_created_at)",
        )
    breakdown["freshness"] = freshness_component

    # ---- employment type (5) --------------------------------------------------
    if not prefs.soft.workplace_types and not prefs.hard.employment_types:
        employment_component = ComponentResult(
            "employment_type", _EMPLOYMENT_MAX, _EMPLOYMENT_MAX,
            "not_requested", "no employment type preference supplied",
        )
    elif features.employment is None:
        employment_component = ComponentResult(
            "employment_type", _EMPLOYMENT_MAX * 0.5, _EMPLOYMENT_MAX,
            "neutral", "employment type unknown",
        )
    elif (
        features.employment in prefs.hard.employment_types
        or features.employment.value in prefs.soft.workplace_types
    ):
        employment_component = ComponentResult(
            "employment_type", float(_EMPLOYMENT_MAX), _EMPLOYMENT_MAX,
            "matched", f"type {features.employment.value} matches preference",
        )
    else:
        employment_component = ComponentResult(
            "employment_type", 0.0, _EMPLOYMENT_MAX,
            "mismatch", f"type {features.employment.value} outside preference",
        )
    breakdown["employment_type"] = employment_component

    # ---- salary (5) ------------------------------------------------------------
    if soft.salary_min is None:
        salary_component = ComponentResult(
            "salary", _SALARY_MAX, _SALARY_MAX,
            "not_requested", "no minimum salary supplied",
        )
    elif features.salary_min is None and features.salary_max is None:
        salary_component = ComponentResult(
            "salary", _SALARY_MAX * 0.5, _SALARY_MAX,
            "neutral", "salary unavailable",
        )
    else:
        currency_ok = (
            features.salary_currency is None
            or features.salary_currency.upper() == soft.salary_currency.upper()
        )
        upper = features.salary_max if features.salary_max is not None else features.salary_min
        meets = currency_ok and upper is not None and upper >= soft.salary_min
        salary_component = ComponentResult(
            "salary", float(_SALARY_MAX) if meets else 0.0, _SALARY_MAX,
            "matched" if meets else "mismatch",
            "range meets minimum salary" if meets else "range below requested minimum",
        )
    breakdown["salary"] = salary_component

    total = sum(
        component.points
        for component in _iter_components(breakdown)
    )

    created_sort = features.created_at.isoformat() if features.created_at else "9999"
    tie_key = (
        -total,
        -title_points,
        -len(required_matches),
        created_sort,
        features.source,
        features.source_job_id,
    )

    return ScoringResult(
        total=round(total, 2),
        breakdown=breakdown,
        matched_skills=tuple(dict.fromkeys(matched)),
        missing_required_skills=tuple(missing_required),
        tie_key=tie_key,
    )


def _iter_components(breakdown: dict[str, Any]):
    for value in breakdown.values():
        if isinstance(value, ComponentResult):
            yield value
        elif isinstance(value, dict):
            yield from value.values()


def hard_locations(prefs: SearchPreferences) -> bool:
    return bool(prefs.hard.locations)


__all__ = ["ComponentResult", "ScoringResult", "score_job"]
