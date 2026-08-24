"""Cover-letter drafting (Phase 12).

Grounded generation: the LLM receives ONLY the candidate's verified fact
summary and the selected job's facts (same sources as match explanations).
It may never invent employers, dates, metrics, or skills. When no LLM is
available a deterministic template letter is produced from those same facts
so the capability still works offline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SYSTEM_PROMPT = (
    "You draft short, professional cover letters. You receive JSON with "
    "candidate_facts and job_facts — VERIFIED DATA ONLY. Use ONLY these "
    "facts: never invent employers, dates, degrees, metrics, tools, or "
    "accomplishments not listed. Address gaps honestly by emphasizing "
    "adjacent strengths instead of fabricating. Tone: confident, specific, "
    "no fluff. Length: 120-180 words. Output JSON {\"letter\": \"...\"} "
    "with greeting and sign-off included."
)

TEMPLATE = """Dear Hiring Team,

I'm applying for the {title} role at {company}. My background aligns
closely with what this position needs{skills_clause}.

{experience_line}

I'd welcome the chance to discuss how my experience can contribute to
your team.

Sincerely,
{candidate_name}
"""


def build_cover_letter_facts(
    state: Mapping[str, Any] | None,
    job_index: int | None,
) -> dict[str, Any]:
    from app.jarvis.job_facts import extract_candidate_facts, extract_job_facts

    return {
        "candidate_facts": extract_candidate_facts(state),
        "job_facts": extract_job_facts(state, job_index),
    }


async def generate_cover_letter(llm: Any, facts: dict[str, Any]) -> str | None:
    """LLM path. Returns None on absence/failure so callers use the template."""
    if llm is None or not getattr(llm, "enabled", False):
        return None
    if not isinstance(facts.get("job_facts"), dict):
        return None
    prompt = json.dumps(facts, ensure_ascii=False)
    try:
        raw = await llm.generate(
            system_prompt=SYSTEM_PROMPT, user_prompt=prompt, json_mode=True
        )
        from app.llm.intent_json import parse_intent_json

        payload = parse_intent_json(raw)
        letter = payload.get("letter") if isinstance(payload, dict) else None
        if isinstance(letter, str) and len(letter.strip()) > 80:
            return letter.strip()
        return None
    except Exception:  # noqa: BLE001 - provider issues fall back to template
        return None


def deterministic_letter(facts: dict[str, Any]) -> str:
    job = facts.get("job_facts") or {}
    cand = facts.get("candidate_facts") or {}
    skills = cand.get("skills") or []
    top = ", ".join(skills[:5]) if skills else "the core requirements"
    matched = [
        s for s in (job.get("required_skills") or []) if s in skills
    ][:4]
    skills_clause = ""
    if matched:
        skills_clause = (
            ", particularly my hands-on experience with "
            + ", ".join(matched)
        )
    elif skills:
        skills_clause = f", including {top}"

    titles = cand.get("recent_titles") or []
    experience_line = (
        f"In my recent work as {' and '.join(titles[:2])}, I have applied "
        "these strengths to deliver practical results."
        if titles
        else "My experience has prepared me to contribute from day one."
    )
    return TEMPLATE.format(
        title=job.get("title", "the advertised"),
        company=job.get("company", "your organization"),
        skills_clause=skills_clause,
        experience_line=experience_line,
        candidate_name=cand.get("name") or "[Your name]",
    )


__all__ = ["build_cover_letter_facts", "deterministic_letter", "generate_cover_letter"]
