"""Facts-only narration input for the optional LLM narrator.

Builds a MINIMAL, verified JSON view of run results. Deliberately excludes:
raw GraphState, job descriptions/requirements bodies, candidate profile,
contact data, resume text, errors with internal detail, credentials.

Everything included originates from Phase 4–6 artifacts the deterministic
narrator already shows users — the LLM may rephrase but never extend them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAX_JOBS = 5


def build_narration_facts(state: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        return {"jobs_found": 0}

    jobs = [j for j in state.get("jobs") or [] if isinstance(j, Mapping)]
    matches = [
        m for m in state.get("match_results") or [] if isinstance(m, Mapping)
    ]

    facts: dict[str, Any] = {"jobs_found": len(jobs), "matches_scored": len(matches)}

    top: list[dict[str, Any]] = []
    for match in matches[:_MAX_JOBS]:
        index = match.get("job_index")
        entry: dict[str, Any] = {
            "rank": int(index) + 1 if isinstance(index, int) else None,
            "score": match.get("score"),
            "tier": match.get("tier"),
        }
        if isinstance(index, int) and 0 <= index < len(jobs):
            entry["title"] = jobs[index].get("title")
            entry["company"] = jobs[index].get("company")
        top.append(entry)
    if top:
        facts["top_matches"] = top

    tailored = state.get("tailored_resume") or {}
    resume = tailored.get("resume") if isinstance(tailored, Mapping) else None
    if isinstance(resume, Mapping):
        summary = (resume.get("summary") or {}).get("text")
        if isinstance(summary, str) and summary.strip():
            facts["tailored_summary"] = summary.strip()
        unaddressed = resume.get("unaddressed_jd_requirements")
        if isinstance(unaddressed, list) and unaddressed:
            facts["unaddressed_requirements"] = [
                str(item) for item in unaddressed[:6]
            ]

    report = state.get("validation_report") or {}
    if isinstance(report, Mapping):
        overall = report.get("overall_status")
        if overall:
            facts["validation_overall"] = str(overall)
        ats_metrics = ((report.get("ats") or {}).get("metrics")) or {}
        required = ats_metrics.get("required_coverage_pct")
        if isinstance(required, (int, float)):
            facts["required_coverage_pct"] = required

    return facts


__all__ = ["build_narration_facts"]
