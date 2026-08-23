"""Deterministic narration: compose the assistant reply from final state.

Reads ONLY non-PII fields (counts, titles, skill names, scores, statuses).
Contact/identity are never touched.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def narrate(state: Mapping[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    """Return (reply_text, attachments[]). Deterministic; no LLM."""
    if not state:
        return "No results yet.", []

    attachments: list[dict[str, Any]] = []
    lines: list[str] = []

    jobs = state.get("jobs") or []
    state.get("ranked_jobs") or []
    matches = state.get("match_results") or []
    tailored_result = state.get("tailored_resume") or {}
    report = state.get("validation_report") or {}

    lines.append(
        f"Discovered {len(jobs)} job(s); top match score "
        f"{matches[0]['score']:g} ({matches[0]['tier']})."
        if matches
        else f"Discovered {len(jobs)} job(s)."
    )

    if matches:
        lines.append("Top matches:")
        for match in matches[:3]:
            index = match["job_index"]
            title = None
            company = None
            if index < len(jobs):
                title = jobs[index].get("title")
                company = jobs[index].get("company")
            lines.append(
                f"  • #{index + 1} {title or 'Untitled'} at {company or 'Unknown'} — "
                f"{match['score']:g}/100 ({match['tier']}, {match['confidence']} confidence)"
            )

    resume = tailored_result.get("resume")
    if isinstance(resume, dict):
        summary_text = (resume.get("summary") or {}).get("text")
        if summary_text:
            lines.append(f"\nTailored summary: {summary_text}")
        unaddressed = resume.get("unaddressed_jd_requirements") or []
        if unaddressed:
            lines.append("JD skills you do not yet show evidence for: " + ", ".join(unaddressed))
        attachments.append({"kind": "tailored_resume", "job_index": resume.get("target_job_index")})

    overall = report.get("overall_status")
    if overall:
        metrics = (report.get("ats") or {}).get("metrics") or {}
        lines.append(
            f"Validation: {overall}"
            + (
                f" — required-skill coverage {metrics['required_coverage_pct']:g}%"
                if "required_coverage_pct" in metrics
                else ""
            )
        )
        attachments.append({"kind": "validation_report", "status": overall})

    errors = state.get("errors") or []
    failed_sources = sorted({error.get("source") for error in errors})
    if failed_sources:
        lines.append("Note: some steps reported errors (" + ", ".join(failed_sources) + ").")

    return "\n".join(lines), attachments


__all__ = ["narrate"]
