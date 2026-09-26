"""Session-scoped container for JARVIS Computer Control state.

Guarantees strict session isolation:
- No shared global computer state between users / connections
- Per-session ComputerState, BrowserSession, TaskManager, TypedContext, ActionCircuitBreaker
- Task generation and cancellation tokens scoped strictly to this session
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.agent.task_manager import TaskManager
from app.computer.circuit_breaker import ActionCircuitBreaker
from app.computer.context import TypedContext
from app.computer.observation import ComputerObservation
from app.desktop.browser_session import BrowserSession
from app.desktop.state import ComputerState


@dataclass
class ComputerSession:
    """Session container isolating computer agent state for a single connection."""

    session_id: str
    created_at: float = field(default_factory=time.time)

    # Isolated state instances
    computer_state: ComputerState = field(default_factory=ComputerState)
    browser_session: BrowserSession = field(default_factory=BrowserSession)
    task_manager: TaskManager = field(default_factory=TaskManager)
    circuit_breaker: ActionCircuitBreaker = field(default_factory=ActionCircuitBreaker)
    typed_context: TypedContext = field(default_factory=TypedContext)

    # Scoped execution metadata
    current_task_id: str | None = None
    current_generation: int = 1
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    last_observation: ComputerObservation | None = None
    is_cancelled: bool = False
    pending_prompt: dict[str, Any] | None = None

    def invalidate_and_cancel_current(self) -> int:
        """Cancel current flight and advance generation."""
        self.is_cancelled = True
        new_gen = self.task_manager.next_generation()
        self.current_generation = new_gen
        self.computer_state.current_generation = new_gen
        return new_gen

    def reset_task_state(self) -> None:
        """Reset circuit breaker and context for a new task while keeping conversational memory."""
        self.circuit_breaker = ActionCircuitBreaker()
        self.is_cancelled = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "current_generation": self.current_generation,
            "active_application": self.computer_state.active_application,
            "current_url": self.computer_state.current_url or self.browser_session.url,
            "current_directory": self.computer_state.current_directory,
            "task_id": self.current_task_id,
            "is_cancelled": self.is_cancelled,
        }


__all__ = ["ComputerSession"]
