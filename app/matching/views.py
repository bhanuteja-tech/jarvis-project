"""Deterministic candidate/job views for matching.

Read-only consumers of frozen contracts:
- ``candidate_profile`` (CandidateResult dump, Phase 3),
- canonical Job dicts,
- ``jd_analyses`` (AnalysisResult dumps, Phase 2).

Job-side normalization (employment enum) reuses the frozen
``ranking.preferences.normalize_employment``. Enum values may arrive as
members or plain strings depending on serialization; every read normalizes
defensively.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.dedup.normalize import location_key as dedup_location_key
from app.ranking.preferences import normalize_employment

_EDU_LADDER: tuple[str, ...] = (
    "bootcamp",
    "diploma",
    "associate",
    "bachelor",
    "master",
    "phd",
)
_LEVEL_LADDER: tuple[str, ...] = (
    "intern",
    "fresher",
    "entry",
    "junior",
    "mid",
    "senior",
    "lead",
    "principal",
)

#: JD level_word -> equivalent minimum years (representation of the JD's own
#: stated level; NEVER presented as candidate experience).
LEVEL_WORD_MIN_YEARS: dict[str, int] = {
    "intern": 0,
    "fresher": 0,
    "entry": 0,
    "junior": 1,
    "mid": 3,
    "senior": 5,
    "lead": 7,
    "principal": 9,
}

_TITLE_TOKEN_RE = re.compile(r"[a-z]+")


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _edu_rank(degree_raw: Any) -> int | None:
    token = str(_val(degree_raw)).lower().strip()
    for index, name in enumerate(_EDU_LADDER):
        if token == name or (token and token.startswith(name)):
            return index
    return None


def _level_rank_from_titles(titles: list[Any]) -> int | None:
    best: int | None = None
    for title in titles:
        tokens = set(_TITLE_TOKEN_RE.findall(str(title).lower()))
        for index, level in enumerate(_LEVEL_LADDER):
            if level in tokens and (best is None or index > best):
                best = index
    return best


def _opt_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


@dataclass(frozen=True)
class CandidateView:
    usable: bool
    skill_names: frozenset[str]
    total_years: float | None
    highest_edu_rank: int | None
    edu_known: bool
    level_rank: int | None
    remote_pref: bool | None
    relocation: bool | None
    location_keys: frozenset[str]
    employment_types: frozenset[str]
    salary_min: float | None
    salary_currency: str | None


_UNUSABLE_CANDIDATE = CandidateView(
    usable=False,
    skill_names=frozenset(),
    total_years=None,
    highest_edu_rank=None,
    edu_known=False,
    level_rank=None,
    remote_pref=None,
    relocation=None,
    location_keys=frozenset(),
    employment_types=frozenset(),
    salary_min=None,
    salary_currency=None,
)


def build_candidate_view(candidate_result: Mapping[str, Any] | None) -> CandidateView:
    if not isinstance(candidate_result, Mapping):
        return _UNUSABLE_CANDIDATE
    status = str(_val(candidate_result.get("status"))).lower()
    profile = candidate_result.get("profile")
    if status not in {"parsed", "partial"} or not isinstance(profile, Mapping):
        return _UNUSABLE_CANDIDATE

    skill_names: set[str] = set()
    titles: list[str] = []

    skills_section = profile.get("skills") or {}
    for item in skills_section.get("items") or []:
        name = item.get("name")
        if name:
            skill_names.add(str(name).strip().lower())

    experience_section = profile.get("experience") or {}
    for item in experience_section.get("items") or []:
        for inner in item.get("skills_in_role") or []:
            inner_name = inner.get("name")
            if inner_name:
                skill_names.add(str(inner_name).strip().lower())
        if item.get("title"):
            titles.append(item["title"])

    projects_section = profile.get("projects") or {}
    for item in projects_section.get("items") or []:
        for tech in item.get("technologies") or []:
            tech_name = tech.get("name")
            if tech_name:
                skill_names.add(str(tech_name).strip().lower())

    education_items = (profile.get("education") or {}).get("items") or []
    edu_ranks = [rank for rank in (_edu_rank(i.get("degree")) for i in education_items) if rank is not None]

    preferences = profile.get("preferences") or {}
    raw_locations = preferences.get("locations") or []
    location_keys = {
        dedup_location_key(str(loc)) or str(loc).strip().lower()
        for loc in raw_locations
        if str(loc).strip()
    }
    employment_types = {
        str(_val(et)).strip().lower() for et in (preferences.get("employment_types") or [])
    }

    salary_min_obj = preferences.get("salary_min")
    salary_min_amount = None
    salary_min_currency = None
    if isinstance(salary_min_obj, Mapping):
        amount = salary_min_obj.get("amount")
        if isinstance(amount, (int, float)):
            salary_min_amount = float(amount)
        currency = salary_min_obj.get("currency")
        if isinstance(currency, str) and currency.strip():
            salary_min_currency = currency.strip().upper()

    total_years = experience_section.get("total_years")
    if not isinstance(total_years, (int, float)) or isinstance(total_years, bool):
        total_years = None

    return CandidateView(
        usable=True,
        skill_names=frozenset(skill_names),
        total_years=total_years,
        highest_edu_rank=max(edu_ranks) if edu_ranks else None,
        edu_known=bool(education_items),
        level_rank=_level_rank_from_titles(titles),
        remote_pref=_opt_bool(preferences.get("remote")),
        relocation=_opt_bool(preferences.get("relocation")),
        location_keys=frozenset(location_keys),
        employment_types=frozenset(employment_types),
        salary_min=salary_min_amount,
        salary_currency=salary_min_currency,
    )


@dataclass(frozen=True)
class JobView:
    job_index: int
    has_analysis: bool

    required_skills: frozenset[str]
    preferred_skills: frozenset[str]

    exp_min_years: int | None
    exp_max_years: int | None
    level_word_floor_years: int | None

    edu_required_rank: int | None

    location_key: str | None
    is_remote_job: bool
    work_mode: str | None

    employment: str | None  # normalized EmploymentType value, or None

    offered_min: float | None
    offered_max: float | None
    offered_currency: str | None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def build_job_view(
    job: Mapping[str, Any],
    job_index: int,
    analysis_result: Mapping[str, Any] | None,
) -> JobView:
    analysis = None
    if isinstance(analysis_result, Mapping):
        candidate_analysis = analysis_result.get("analysis")
        if isinstance(candidate_analysis, Mapping):
            analysis = candidate_analysis
    has_analysis = (
        analysis is not None
        and str(_val(analysis_result.get("status"))).lower() in {"analyzed", "partial"}
    )

    required: set[str] = set()
    preferred: set[str] = set()
    exp_min = exp_max = None
    level_word_floor = None
    edu_required_rank = None

    if has_analysis:
        skills_section = analysis.get("skills") or {}
        for item in skills_section.get("required") or []:
            name = item.get("name")
            if name:
                required.add(str(name).strip().lower())
        for item in skills_section.get("preferred") or []:
            name = item.get("name")
            if name:
                preferred.add(str(name).strip().lower())

        experience = analysis.get("experience") or {}
        exp_min = experience.get("min_years")
        exp_max = experience.get("max_years")
        exp_min = exp_min if isinstance(exp_min, int) else None
        exp_max = exp_max if isinstance(exp_max, int) else None
        level_word = experience.get("level_word")
        if level_word:
            token = re.findall(r"[a-z]+", str(level_word).lower())
            for candidate in token:
                if candidate in LEVEL_WORD_MIN_YEARS:
                    level_word_floor = LEVEL_WORD_MIN_YEARS[candidate]
                    break

        education_items = (analysis.get("education") or {}).get("items") or []
        edu_ranks = [
            rank for rank in (_edu_rank(i.get("degree")) for i in education_items) if rank is not None
        ]
        edu_required_rank = max(edu_ranks) if edu_ranks else None

    # ---- location / remote -------------------------------------------------
    work_mode = None
    remote_eligibility = None
    job_location_text = job.get("location")
    if has_analysis:
        arrangement = analysis.get("work_arrangement") or {}
        raw_mode = arrangement.get("mode")
        work_mode = str(_val(raw_mode)).lower() if raw_mode is not None else None
        location_section = analysis.get("location") or {}
        remote_eligibility = _opt_bool(location_section.get("remote_eligibility"))
        jd_job_location = location_section.get("job_location")
        if isinstance(jd_job_location, str) and jd_job_location.strip():
            job_location_text = jd_job_location

    location_key_value = dedup_location_key(job_location_text)
    is_remote_job = (
        location_key_value == "remote"
        or remote_eligibility is True
        or work_mode == "remote"
    )

    # ---- employment ----------------------------------------------------------
    employment_value = None
    if has_analysis:
        employment_info = analysis.get("employment_type") or {}
        raw_value = employment_info.get("value")
        if isinstance(raw_value, str) and raw_value.strip():
            employment_value = normalize_employment(raw_value)
    if employment_value is None:
        employment_value = normalize_employment(job.get("employment_type"))
    employment_str = employment_value.value if employment_value is not None else None

    # ---- salary ----------------------------------------------------------------
    offered_min = offered_max = None
    offered_currency = None
    if has_analysis:
        salary = analysis.get("salary") or {}
        offered_min = _num(salary.get("canonical_min"))
        offered_max = _num(salary.get("canonical_max"))
        currency = salary.get("canonical_currency")
        offered_currency = currency.upper() if isinstance(currency, str) and currency else None
        parsed = salary.get("parsed_from_text")
        if (offered_min is None and offered_max is None) and isinstance(parsed, Mapping):
            offered_min = _num(parsed.get("min"))
            offered_max = _num(parsed.get("max"))
            parsed_currency = parsed.get("currency")
            if offered_currency is None and isinstance(parsed_currency, str):
                offered_currency = parsed_currency.upper() or None

    return JobView(
        job_index=job_index,
        has_analysis=has_analysis,
        required_skills=frozenset(required),
        preferred_skills=frozenset(preferred),
        exp_min_years=exp_min,
        exp_max_years=exp_max,
        level_word_floor_years=level_word_floor,
        edu_required_rank=edu_required_rank,
        location_key=location_key_value,
        is_remote_job=is_remote_job,
        work_mode=work_mode,
        employment=employment_str,
        offered_min=offered_min,
        offered_max=offered_max,
        offered_currency=offered_currency,
    )


__all__ = ["JobView", "CandidateView", "build_candidate_view", "build_job_view"]
