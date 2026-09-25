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
    #: Phase 11: real routing visibility (provider that handled the request).
    LLM_PROVIDER_SELECTED = "llm_provider_selected"
    #: Emitted ONLY when a routed provider failed BEFORE the first delta and
    #: the chain moved on — never after real tokens were streamed.
    LLM_FALLBACK = "llm_fallback"
    TOKEN = "token"
    ASSISTANT_MESSAGE = "assistant_message"
    LISTENING_STARTED = "listening_started"
    LISTENING_STOPPED = "listening_stopped"
    RUN_CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"
    #: Phase 8: desktop control action result (open app, screenshot, etc.)
    DESKTOP_ACTION_RESULT = "desktop_action_result"
    # -----------------------------------------------------------------------
    # Phase 8+ (Semantic Computer-Use Agent)
    # -----------------------------------------------------------------------
    #: Planning phase started (user utterance received, building task plan)
    COMPUTER_PLAN_START = "computer_plan_start"
    #: Plan was built successfully — includes step list
    COMPUTER_PLAN_READY = "computer_plan_ready"
    #: A single step in the plan is about to execute
    COMPUTER_STEP_START = "computer_step_start"
    #: A step completed and was verified
    COMPUTER_STEP_DONE = "computer_step_done"
    #: A step completed but verification failed
    COMPUTER_STEP_FAILED = "computer_step_failed"
    #: A high-risk step requires user confirmation before proceeding
    COMPUTER_NEEDS_CONFIRM = "computer_needs_confirm"
    #: Final truthful response (always gated on verification status)
    COMPUTER_RESPONSE = "computer_response"
    #: Unrecoverable computer-agent error
    COMPUTER_ERROR = "computer_error"
    #: Part 13: Real-time computer state and context updates
    COMPUTER_STATE_UPDATE = "computer_state_update"
    COMPUTER_CONTEXT_UPDATE = "computer_context_update"
    COMPUTER_STEP_STARTED = "computer_step_started"
    COMPUTER_STEP_VERIFIED = "computer_step_verified"
    CONFIRMATION_REQUIRED = "confirmation_required"


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
