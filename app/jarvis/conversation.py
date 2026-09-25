"""General conversational agent (Phase 12).

A DEDICATED chat path, separate from the career workflow:
- streams genuine provider tokens
- keeps session conversation memory
- receives NO tools and NO job-search state unless explicitly grounded
- may mention capabilities honestly but never fabricates job results

The career agent (existing Phase 1-6 graph) remains a separate capability
invoked only by explicit intents.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.jarvis.memory import recent_messages, remember_turn

SYSTEM_PROMPT = (
    "You are JARVIS, a warm, concise AI career and desktop automation assistant. "
    "You can: search jobs, analyze and tailor resumes, draft cover letters, "
    "control desktop applications, launch browsers, search the web (Google, YouTube, etc.), "
    "and open user accounts like GitHub and LinkedIn.\n"
    "Rules:\n"
    "- Answer general questions directly and helpfully.\n"
    "- Never claim you cannot interact with desktop apps, browsers, or YouTube "
    "— you have built-in automation tools.\n"
    "- NEVER invent fake job listings, companies, or application statuses.\n"
    "- Keep replies short (1-4 sentences) unless asked for depth."
)

DETERMINISTIC_REPLIES = {
    "casual_chat": [
        (
            "hi",
            "Hello! I'm JARVIS — I can find jobs, analyze or tailor your "
            "resume, and help you prepare. What would you like to do?",
        ),
        (
            "hello",
            "Hi there! Ask me to find roles, review your resume, or "
            "explain anything career-related.",
        ),
        ("thanks", "Anytime! Want me to look for matching roles next?"),
    ],
    "general_question": [
        (
            None,
            "I can answer that once an LLM provider is connected. Right now "
            "I'm running in deterministic mode — try 'help' to see what works "
            "offline, or connect Ollama/OpenAI in settings.",
        )
    ],
}


def deterministic_reply(intent: str, text: str, resume_context: str | None = None) -> str | None:
    """Offline answers for the simplest conversational intents."""
    lowered = text.strip().lower().rstrip("!.")
    resume_cues = (
        "see my resume", "uploaded my resume", "uploaded resume",
        "get my resume", "view my resume", "have my resume", "access my resume",
    )
    if any(phrase in lowered for phrase in resume_cues):
        if resume_context and "successfully parsed" in resume_context:
            return (
                "Yes! Your resume has been uploaded and parsed into your Candidate Profile. "
                "You can see your extracted skills, experience, education, and projects in "
                "the Resume Workspace panel on the right."
            )
        if resume_context and "uploaded" in resume_context:
            return "Yes, a resume file was uploaded in this session and processed."
        return (
            "No resume has been uploaded yet in this session. You can upload your resume "
            "(PDF, DOCX, TXT) anytime using the paperclip button or drag & drop."
        )

    if intent == "casual_chat":
        for cue, reply in DETERMINISTIC_REPLIES["casual_chat"]:
            if lowered == cue or lowered.startswith(cue + " ") is False and lowered == cue:
                return reply
        if any(cue in lowered for cue in ("thank",)):
            return DETERMINISTIC_REPLIES["casual_chat"][2][1]
        return None
    if intent == "general_question" and lowered in {"what can you do", "who are you"}:
        return (
            "I'm JARVIS, your career assistant: I search real job boards, "
            "analyze and tailor resumes with evidence checks, explain match "
            "reasons, draft cover letters, and coach interview prep. "
            "Connect an LLM (e.g. local Ollama) for free-form Q&A too."
        )
    if intent == "general_question":
        return DETERMINISTIC_REPLIES["general_question"][0][1]
    return None


@dataclass(frozen=True)
class ConversationResult:
    text: str
    tokens: int
    duration_ms: float
    streamed: bool


async def converse(
    llm: Any,
    *,
    history: list[dict[str, Any]],
    user_text: str,
    on_delta: Any = None,
    system_override: str | None = None,
    resume_context: str | None = None,
) -> ConversationResult | None:
    """One conversational turn. Returns None when no LLM is available.

    NOTE: history ownership belongs to the caller — this function reads
    ``history`` for context but never mutates it.
    """
    if llm is None or not getattr(llm, "enabled", False):
        return None

    messages = recent_messages(history)
    system = system_override or SYSTEM_PROMPT
    if resume_context:
        system = f"{system}\n\n[Active Session Resume Context]: {resume_context}"
    started = time.perf_counter()
    collected: list[str] = []

    # Adapters expose fixed signatures (system_prompt/user_prompt); recent
    # turns are folded into the prompt so every provider works unchanged.
    flat_prompt = _render_history(user_text, messages[:-1])

    async def _consume(gen: AsyncIterator[str]) -> str:
        async for delta in gen:
            collected.append(delta)
            if on_delta is not None:
                outcome = on_delta(delta)
                if hasattr(outcome, "__await__"):
                    await outcome
        return "".join(collected).strip()

    try:
        if hasattr(llm, "stream"):
            text_out = await _consume(llm.stream(system_prompt=system, user_prompt=flat_prompt))
        else:
            text_out = await llm.generate(system_prompt=system, user_prompt=flat_prompt)
    except Exception:  # noqa: BLE001 - provider failure must not break the turn
        return None

    if not text_out:
        return None

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    remember_turn(history, "assistant", text_out)
    return ConversationResult(
        text=text_out,
        tokens=len(collected),
        duration_ms=duration_ms,
        streamed=bool(collected),
    )


def _render_history(current: str, prior: list[dict[str, str]]) -> str:
    if not prior:
        return current
    lines = ["Recent conversation (context):"]
    for turn in prior[-8:]:
        role = "User" if turn["role"] == "user" else "JARVIS"
        snippet = turn["content"][:400]
        lines.append(f"{role}: {snippet}")
    lines.append("")
    lines.append("User now:")
    lines.append(current)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-intent personas + offline answers
# ---------------------------------------------------------------------------

SYSTEM_PERSONAS = {
    "casual_chat": SYSTEM_PROMPT,
    "general_question": (
        "You are JARVIS, an AI career assistant that also answers general "
        "questions clearly and accurately. Be concise (1-5 sentences). If a "
        "question is about jobs/resumes, mention what you can do with real "
        "tools. Never invent job listings or application statuses."
    ),
    "career_advice": (
        "You are JARVIS, an experienced career coach. Give practical, "
        "specific, encouraging advice. Structure longer answers with short "
        "bullets. Never invent specific job listings or company names as if "
        "from real data; speak generally unless the user shares details."
    ),
}


def _deterministic_job_answer(
    facts: dict[str, Any], candidate: dict[str, Any], question: str
) -> str:
    """Grounded summary from verified facts when no LLM is available."""
    parts: list[str] = []
    title = facts.get("title") or "this role"
    company = facts.get("company") or ""
    parts.append(f"{title}" + (f" at {company}" if company else ""))
    if facts.get("location"):
        parts[0] += f" ({facts['location']})"

    matched = facts.get("matched_skills") or []
    skills = candidate.get("skills") or []
    overlap = [s for s in matched if s in skills] or matched[:4]
    if overlap:
        parts.append(
            "Your strengths here: " + ", ".join(overlap)
        )
    missing = facts.get("missing_requirements")
    if missing:
        parts.append("Gaps to address: " + ", ".join(missing))
    if isinstance(facts.get("match_score"), (int, float)):
        parts.append(f"Overall match score: {facts['match_score']:g}/100.")
    reasons = facts.get("match_reasons") or []
    if reasons:
        parts.append("; ".join(reasons[:3]))
    if len(parts) == 1:
        parts.append(
            "Run a search with your resume uploaded for a personalized match."
        )
    return ". ".join(parts) + "."


__all__ = [
    "ConversationResult",
    "SYSTEM_PERSONAS",
    "_deterministic_job_answer",
    "converse",
    "deterministic_reply",
]
