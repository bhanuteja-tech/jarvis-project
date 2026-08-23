"""In-memory session store (Phase 7 decision: no persistence).

One session holds the conversation history plus the artifacts needed for
multi-turn interaction (the candidate input survives between messages so a
user can say "now tailor job 2" without re-uploading). Sessions are
process-local and intentionally lost on restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class Session:
    session_id: str
    created_at: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    candidate_input: dict[str, Any] | None = None
    last_state: dict[str, Any] | None = None

    def append_message(self, role: str, text: str) -> None:
        self.messages.append(
            {
                "role": role,
                "text": text,
                "ts": datetime.now(UTC).isoformat(),
            }
        )


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None = None) -> Session:
        key = session_id or str(uuid4())
        if key not in self._sessions:
            self._sessions[key] = Session(
                session_id=key,
                created_at=datetime.now(UTC).isoformat(),
            )
        return self._sessions[key]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)


__all__ = ["InMemorySessionStore", "Session"]
