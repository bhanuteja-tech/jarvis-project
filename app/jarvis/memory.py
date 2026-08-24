"""Session conversation memory for the JARVIS assistant.

Deliberately simple: a bounded rolling window of dialogue turns kept on the
Session object. No vector database, no persistence — restarts forget, which
matches every other Phase 7+ in-memory structure (documented behaviour).
"""

from __future__ import annotations

from typing import Any

MAX_TURNS = 24  # user+assistant pairs kept per session


def remember_turn(history: list[dict[str, Any]], role: str, content: str) -> None:
    """Append one dialogue turn, trimming to the window."""
    history.append({"role": role, "content": content})
    while len(history) > MAX_TURNS:
        history.pop(0)


def recent_messages(
    history: list[dict[str, Any]], *, max_messages: int = 12
) -> list[dict[str, str]]:
    """LLM-ready message slice (oldest -> newest), alternating-friendly."""
    clean: list[dict[str, str]] = []
    for turn in history[-max_messages:]:
        role = turn.get("role")
        content = turn.get("content") or ""
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            clean.append({"role": role, "content": content})
    return clean


__all__ = ["MAX_TURNS", "recent_messages", "remember_turn"]
