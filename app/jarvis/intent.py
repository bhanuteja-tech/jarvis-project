"""Deterministic intent parsing (chat text -> plan action).

v1 uses a command/grammar parser only — no LLM. An optional
``AssistantLlmClient`` protocol seam exists for natural-language fallback,
disabled by default; no provider is implemented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Plan:
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    reply_hint: str | None = None


_ACTIONS = ("run_discovery", "select_target", "get_results", "help")


@runtime_checkable
class AssistantLlmClient(Protocol):
    async def parse_intent(self, *, text: str, grammar_help: str) -> dict[str, Any]: ...


class DisabledAssistantLlmClient:
    enabled = False

    async def parse_intent(self, *, text: str, grammar_help: str) -> dict[str, Any]:
        raise RuntimeError("assistant LLM is disabled by configuration")


_SELECT_TARGET_RE = re.compile(r"(?:tailor|use|pick|select)\s+(?:job\s+|match\s+|#)?(\d{1,3})", re.IGNORECASE)
_IN_RE = re.compile(r"\bin\s+([A-Za-z ,]+)$", re.IGNORECASE)


def parse_intent(text: str) -> Plan:
    """Deterministic grammar. Never raises."""
    cleaned = (text or "").strip()
    lowered = cleaned.lower()

    match = _SELECT_TARGET_RE.match(lowered)
    if match:
        return Plan(
            action="select_target",
            params={"target_job_index": int(match.group(1)) - 1},
            reply_hint=f"Re-running with target job #{match.group(1)}.",
        )

    if lowered in {"status", "results", "show results"}:
        return Plan(action="get_results")

    if lowered in {"help", "?"}:
        return Plan(action="help")

    if lowered.startswith(("find ", "search ")):
        params: dict[str, Any] = {"user_query": cleaned}
        location_match = _IN_RE.search(cleaned)
        if location_match is not None:
            locations = [
                part.strip()
                for part in location_match.group(1).split(",")
                if part.strip()
            ]
            params["locations"] = locations
        return Plan(
            action="run_discovery",
            params=params,
            reply_hint="Starting job discovery.",
        )

    # Non-command free text still triggers discovery using the whole message
    # as the query (deterministic default; NL fallback requires enabling the
    # assistant LLM).
    return Plan(
        action="run_discovery",
        params={"user_query": cleaned},
        reply_hint="Interpreting your message as a job search.",
    )


GRAMMAR_HELP = (
    "You can say:\n"
    "- find machine learning engineer in berlin\n"
    "- tailor job 1   (or: use match 1)\n"
    "- status\n"
    "- help"
)


__all__ = ["AssistantLlmClient", "DisabledAssistantLlmClient", "Plan", "GRAMMAR_HELP", "parse_intent"]
