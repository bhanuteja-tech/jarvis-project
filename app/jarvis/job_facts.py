"""Verified-fact extraction for job/candidate grounding.

Everything an LLM may be told about a job or the candidate flows through
here. Deliberately excludes: contact data, raw resume text, full JD bodies,
internal errors, credentials.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAX_REQ_CHARS = 220


def _job_at(state: Mapping[str, Any] | None, index: int | None) -> dict[str, Any] | None:
    if not isinstance(state, Mapping) or not isinstance(index, int):
        return None
    jobs = [j for j in state.get("jobs") or [] if isinstance(j, Mapping)]
    if 0 <= index < len(jobs):
        return dict(jobs[index])
    return None


def selected_job_index(
    state: Mapping[str, Any] | None,
    *,
    explicit: int | None = None,
) -> int | None:
    """Resolve which job 'this job' refers to: explicit > tailored target > best match."""
    jobs = [j for j in (state or {}).get("jobs") or [] if isinstance(j, Mapping)]
    if not jobs:
        return None
    if isinstance(explicit, int):
        return explicit if 0 <= explicit < len(jobs) else None
    tailored = ((state.get("tailored_resume") or {}).get("resume") or {}).get("target_job_index")
    if isinstance(tailored, int) and 0 <= tailored < len(jobs):
        return tailored
    matches = [
        m
        for m in state.get("match_results") or []
        if isinstance(m, Mapping) and isinstance(m.get("score"), (int, float))
    ]
    if matches:
        best = max(matches, key=lambda m: m["score"])
        idx = best.get("job_index")
        if isinstance(idx, int):
            return idx
    return 0


def extract_job_facts(
    state: Mapping[str, Any] | None, index: int | None = None
) -> dict[str, Any] | None:
    job = _job_at(state, index)
    if job is None:
        return None

    facts: dict[str, Any] = {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "url": job.get("job_url") or job.get("apply_url"),
        "source": job.get("source"),
    }
    facts = {k: v for k, v in facts.items() if v}

    requirements = job.get("requirements")
    if isinstance(requirements, list):
        reqs = [str(r)[:_MAX_REQ_CHARS] for r in requirements[:10]]
        if reqs:
            facts["requirements_sample"] = reqs
    responsibilities = job.get("responsibilities")
    if isinstance(responsibilities, list):
        resp = [str(r)[:_MAX_REQ_CHARS] for r in responsibilities[:8]]
        if resp:
            facts["responsibilities_sample"] = resp

    # Match information, when this job was scored against the candidate.
    for match in state.get("match_results") or []:
        if isinstance(match, Mapping) and match.get("job_index") == (
            index if isinstance(index, int) else -1
        ):
            facts["match_score"] = match.get("score")
            facts["matched_skills"] = [str(s) for s in (match.get("matched_skills") or [])[:12]]
            missing = [str(s) for s in (match.get("missing_required") or [])[:8]]
            if missing:
                facts["missing_requirements"] = missing
            breakdown = match.get("breakdown")
            if isinstance(breakdown, Mapping):
                reasons = []
                for component, detail in list(breakdown.items())[:6]:
                    reason = detail.get("reason") if isinstance(detail, Mapping) else ""
                    if reason:
                        reasons.append(f"{component}: {reason}")
                if reasons:
                    facts["match_reasons"] = reasons
            break

    jd = state.get("jd_analyses") or []
    if isinstance(index, int) and index < len(jd) and isinstance(jd[index], Mapping):
        analysis = jd[index].get("analysis") or {}
        skills = (analysis.get("skills") or {}) if isinstance(analysis, Mapping) else {}
        req_items = skills.get("required", [])
        required = [str(s.get("name")) for s in req_items if isinstance(s, Mapping)]
        if required:
            facts["required_skills"] = required[:12]
    return facts


def extract_candidate_facts(state: Mapping[str, Any] | None) -> dict[str, Any]:
    profile = (state or {}).get("candidate_profile") or {}
    inner = profile.get("profile") if isinstance(profile, Mapping) else None
    inner = inner if isinstance(inner, Mapping) else {}

    skill_items = (
        inner.get("skills", {}).get("items", []) if isinstance(inner.get("skills"), Mapping) else []
    )
    skills = [str(s.get("name")) for s in skill_items if isinstance(s, Mapping)]
    experience = inner.get("experience", {}) if isinstance(inner.get("experience"), Mapping) else {}
    titles: list[str] = []
    companies: list[str] = []
    exp_items = experience.get("items", []) if isinstance(experience.get("items"), list) else []
    for item in exp_items:
        if isinstance(item, Mapping):
            if item.get("title"):
                titles.append(str(item["title"]))
            if item.get("company"):
                companies.append(str(item["company"]))
    edu_items = (
        inner.get("education", {}).get("items", [])
        if isinstance(inner.get("education"), Mapping)
        else []
    )
    education = [str(e.get("degree")) for e in edu_items if isinstance(e, Mapping)]

    facts: dict[str, Any] = {
        "has_resume": bool(state and state.get("candidate_input")),
        "skills": skills[:20],
        "experience_count": len(titles),
        "recent_titles": titles[:4],
    }
    if education:
        facts["education"] = education[:3]
    years = experience.get("total_years")
    if isinstance(years, (int, float)):
        facts["total_years"] = years

    # Match summary across last run (what the candidate is strong/weak for).
    matches = [m for m in (state or {}).get("match_results") or [] if isinstance(m, Mapping)]
    strong = sorted(
        (m for m in matches if isinstance(m.get("score"), (int, float))),
        key=lambda m: m["score"],
        reverse=True,
    )
    if strong:
        facts["best_match_score"] = strong[0]["score"]
        facts["strong_matches_count"] = sum(
            1 for m in matches if isinstance(m.get("tier"), str) and m["tier"] == "strong"
        )
    return facts


__all__ = ["extract_candidate_facts", "extract_job_facts", "selected_job_index"]
