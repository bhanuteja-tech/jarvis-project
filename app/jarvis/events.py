"""Typed WebSocket event envelopes for the Jarvis interface layer.

One envelope shape for every event category:

    {"type": str, "seq": int, "ts": iso8601, "run_id": str|None, "data": {...}}

Unknown event types must be ignored by clients (forward compatibility).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    AGENT_STARTED = "agent_started"
    AGENT_THINKING = "agent_thinking"
    AGENT_SPEAKING = "agent_speaking"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_COMPLETED = "tool_completed"
    WORKFLOW_NODE_STARTED = "workflow_node_started"
    WORKFLOW_NODE_COMPLETED = "workflow_node_completed"
    TOKEN = "token"
    ASSISTANT_MESSAGE = "assistant_message"
    LISTENING_STARTED = "listening_started"
    LISTENING_STOPPED = "listening_stopped"
    RUN_CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


def make_event(
    event_type: EventType | str,
    *,
    seq: int,
    run_id: str | None = None,
    **data: Any,
) -> dict[str, Any]:
    return {
        "type": event_type.value if isinstance(event_type, EventType) else str(event_type),
        "seq": seq,
        "ts": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "data": data,
    }


__all__ = ["EventType", "make_event"]
