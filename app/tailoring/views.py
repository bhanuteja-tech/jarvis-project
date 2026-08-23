"""Views over frozen Phase 2/3/4 dumps for tailoring.

Read-only consumers of:
- ``candidate_profile`` (CandidateResult dump, Phase 3),
- ``match_results`` (MatchResult dumps, Phase 4),
- ``jd_analyses`` (AnalysisResult dumps, Phase 2),
- canonical Job dicts (target title/company echo).

All reads normalize enum-vs-string defensively. PII blocks are never read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class SkillRef:
    name: str  # canonical taxonomy name (lowercase)
    display: str  # candidate's matched_as spelling


@dataclass(frozen=True)
class ExpRef:
    index: int
    title: str | None
    company: str | None
    date_range: str | None
    highlights: tuple[str, ...]
    duration_months: int | None
    skill_names: frozenset[str]


@dataclass(frozen=True)
class ProjRef:
    index: int
    name: str | None
    description: str | None
    url: str | None
    tech_names: tuple[str, ...]


@dataclass(frozen=True)
class ProfileView:
    usable: bool
    profile_id: str | None
    summary_text: str | None
    skills: tuple[SkillRef, ...]
    experience: tuple[ExpRef, ...]
    projects: tuple[ProjRef, ...]
    education_items: tuple[dict[str, Any], ...]
    certification_names: tuple[str, ...]


_UNUSABLE_PROFILE = ProfileView(
    usable=False,
    profile_id=None,
    summary_text=None,
    skills=(),
    experience=(),
    projects=(),
    education_items=(),
    certification_names=(),
)


def _skill_refs(items: Any) -> list[SkillRef]:
    refs: list[SkillRef] = []
    for item in items or []:
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            refs.append(
                SkillRef(
                    name=name.strip().lower(),
                    display=str(item.get("matched_as") or name).strip(),
                )
            )
    return refs


def build_profile_view(candidate_result: Mapping[str, Any] | None) -> ProfileView:
    if not isinstance(candidate_result, Mapping):
        return _UNUSABLE_PROFILE
    status = str(_val(candidate_result.get("status"))).lower()
    profile = candidate_result.get("profile")
    if status not in {"parsed", "partial"} or not isinstance(profile, Mapping):
        return _UNUSABLE_PROFILE

    summary_section = profile.get("summary") or {}
    summary_text = (
        str(summary_section.get("text")).strip()
        if isinstance(summary_section.get("text"), str) and summary_section["text"].strip()
        else None
    )

    experience_items: list[ExpRef] = []
    exp_section = profile.get("experience") or {}
    for index, item in enumerate(exp_section.get("items") or []):
        highlights = tuple(
            h.strip() for h in (item.get("highlights") or []) if isinstance(h, str) and h.strip()
        )
        skill_names = {
            str(_val(inner.get("name"))).strip().lower()
            for inner in item.get("skills_in_role") or []
            if inner.get("name")
        }
        start_raw = item.get("start_raw")
        end_raw = item.get("end_raw")
        date_range = (
            f"{start_raw} - {end_raw}"
            if isinstance(start_raw, str) and isinstance(end_raw, str)
            else None
        )
        duration = item.get("duration_months")
        experience_items.append(
            ExpRef(
                index=index,
                title=item.get("title"),
                company=item.get("company"),
                date_range=date_range,
                highlights=highlights,
                duration_months=duration if isinstance(duration, int) else None,
                skill_names=frozenset(skill_names),
            )
        )

    project_items: list[ProjRef] = []
    projects_section = profile.get("projects") or {}
    for index, item in enumerate(projects_section.get("items") or []):
        tech_names = tuple(
            str(_val(tech.get("name"))).strip().lower()
            for tech in item.get("technologies") or []
            if tech.get("name")
        )
        description = item.get("description")
        project_items.append(
            ProjRef(
                index=index,
                name=item.get("name"),
                description=description if isinstance(description, str) else None,
                url=item.get("url") if isinstance(item.get("url"), str) else None,
                tech_names=tech_names,
            )
        )

    education_items = tuple(
        education_item
        for education_item in (profile.get("education") or {}).get("items") or []
        if isinstance(education_item, dict)
    )
    certification_names = tuple(
        str(cert.get("name"))
        for cert in (profile.get("certifications") or {}).get("items") or []
        if cert.get("name")
    )

    return ProfileView(
        usable=True,
        profile_id=str(profile.get("profile_id")) if profile.get("profile_id") else None,
        summary_text=summary_text,
        skills=tuple(_skill_refs((profile.get("skills") or {}).get("items"))),
        experience=tuple(experience_items),
        projects=tuple(project_items),
        education_items=education_items,
        certification_names=certification_names,
    )


# ---------------------------------------------------------------------------
# Target job resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetView:
    job_index: int
    job_ref: dict[str, Any]
    title: str | None
    company: str | None
    has_analysis: bool
    required_skills: frozenset[str]
    preferred_skills: frozenset[str]
    responsibilities_text: str


@dataclass(frozen=True)
class TargetResolution:
    target: TargetView | None
    error_reason: str | None
    analysis_missing: bool


def resolve_target(
    match_results: SequenceLike,
    jd_analyses: SequenceLike,
    jobs: SequenceLike,
    override_index: int | None,
) -> TargetResolution:
    """Resolve the target job.

    - Default: first entry of ``match_results`` (best match), preferring a
      job whose JD analysis is available.
    - Override: ``search_preferences['tailoring']['target_job_index']``; an
      invalid explicit override FAILS the run.
    """
    analyses_by_index: dict[int, dict[str, Any]] = {}
    for entry in jd_analyses or []:
        index_value = entry.get("job_index")
        if isinstance(index_value, int):
            analyses_by_index.setdefault(index_value, entry)

    def analysis_for(index: int) -> tuple[bool, dict[str, Any]]:
        entry = analyses_by_index.get(index)
        analysis = entry.get("analysis") if isinstance(entry, Mapping) else None
        has_analysis = (
            analysis is not None
            and isinstance(entry, Mapping)
            and str(_val(entry.get("status"))).lower() in {"analyzed", "partial"}
        )
        return has_analysis, (analysis or {})

    def build_target(index: int) -> TargetResolution:
        if not (0 <= index < len(jobs)):
            return TargetResolution(None, "invalid_target_job_index", True)
        job = jobs[index]
        has_analysis, analysis = analysis_for(index)
        required: set[str] = set()
        preferred: set[str] = set()
        responsibility_lines: list[str] = []
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
            resp_section = analysis.get("responsibilities") or {}
            for item in resp_section.get("items") or []:
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    responsibility_lines.append(text_value)

        job_ref = {"source": job.get("source"), "source_job_id": job.get("source_job_id")}
        target = TargetView(
            job_index=index,
            job_ref=job_ref,
            title=job.get("title") if isinstance(job.get("title"), str) else None,
            company=job.get("company") if isinstance(job.get("company"), str) else None,
            has_analysis=has_analysis,
            required_skills=frozenset(required),
            preferred_skills=frozenset(preferred),
            responsibilities_text="\n".join(responsibility_lines),
        )
        return TargetResolution(target=target, error_reason=None, analysis_missing=not has_analysis)

    results = list(match_results or [])
    if not results:
        return TargetResolution(None, "no_matches", True)

    if override_index is not None:
        if not isinstance(override_index, int) or not (0 <= override_index < len(jobs)):
            return TargetResolution(None, "invalid_target_job_index", True)
        return build_target(override_index)

    # Default: best match first; prefer entries whose analysis is available.
    ordered = sorted(
        enumerate(results),
        key=lambda pair: (
            0
            if str(_val(pair[1].get("status"))).lower() in {"analyzed", "partial"}
            and pair[1].get("analysis")
            else 1
        ),
    )
    fallback_error: str | None = None
    for _, wrapper in ordered:
        index_value = wrapper.get("job_index")
        if not isinstance(index_value, int):
            continue
        resolution = build_target(index_value)
        if resolution.error_reason is not None:
            fallback_error = resolution.error_reason
            continue
        if resolution.analysis_missing:
            fallback_error = "jd_analysis_missing"
            continue
        return resolution

    # All candidates lack analysis: degrade to the first valid one (PARTIAL).
    for _, wrapper in ordered:
        index_value = wrapper.get("job_index")
        if isinstance(index_value, int):
            return build_target(index_value)
    return TargetResolution(None, fallback_error or "invalid_target_job_index", True)


class SequenceLike(list):
    """Typing helper alias used by resolve_target parameters."""


__all__ = [
    "ExpRef",
    "ProfileView",
    "ProjRef",
    "SkillRef",
    "TargetResolution",
    "TargetView",
    "build_profile_view",
    "resolve_target",
]
