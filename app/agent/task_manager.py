"""Task Manager for tracking, planning, and cancelling agent actions.

Manages task generations to prevent stale task results from overwriting newer
commands, and provides asynchronous cancellation tokens for multi-step plans.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class TaskLifecycle(StrEnum):
    """Rigorous task lifecycle states."""

    IDLE = "idle"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


@dataclass
class AgentTask:
    """Represents a scheduled or active agent task."""

    task_id: str
    generation: int
    intent: str
    goal: str = ""
    # pending, running, completed, cancelled, failed, stale, waiting_for_user
    status: str = "pending"
    lifecycle_state: str = TaskLifecycle.UNDERSTANDING.value
    current_step: int = 1
    total_steps: int = 1
    parent_task_id: str | None = None
    cancellation_event: asyncio.Event = field(default_factory=asyncio.Event)
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def transition_to(self, state: TaskLifecycle | str) -> None:
        """Advance the task lifecycle state."""
        val = state.value if isinstance(state, TaskLifecycle) else str(state)
        self.lifecycle_state = val
        if val in {
            TaskLifecycle.COMPLETED.value,
            TaskLifecycle.FAILED.value,
            TaskLifecycle.CANCELLED.value,
            TaskLifecycle.STALE.value,
            TaskLifecycle.WAITING_FOR_USER.value,
        }:
            self.status = val

    def cancel(self) -> None:
        """Mark task as cancelled and fire cancellation event."""
        self.status = "cancelled"
        self.lifecycle_state = TaskLifecycle.CANCELLED.value
        self.cancellation_event.set()

    def mark_stale(self) -> None:
        """Mark task as stale and fire cancellation event to abort execution."""
        self.status = "stale"
        self.lifecycle_state = TaskLifecycle.STALE.value
        self.cancellation_event.set()

    def is_cancelled(self) -> bool:
        """Check whether task or its cancellation token has been signalled."""
        return (
            self.status in {"cancelled", "stale"}
            or self.lifecycle_state in {TaskLifecycle.CANCELLED.value, TaskLifecycle.STALE.value}
            or self.cancellation_event.is_set()
        )

    def is_stale(self) -> bool:
        """Check whether task is marked stale due to a new command/generation."""
        return self.status == "stale" or self.lifecycle_state == TaskLifecycle.STALE.value

    def complete(self, result: dict[str, Any]) -> None:
        """Mark task as completed with result."""
        self.status = "completed"
        self.lifecycle_state = TaskLifecycle.COMPLETED.value
        self.result = result
        self.completed_at = time.time()

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = "failed"
        self.lifecycle_state = TaskLifecycle.FAILED.value
        self.result = {"error": error}
        self.completed_at = time.time()


class TaskManager:
    """Central authority for task tracking, generation invalidation, and cancellation."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._current_generation: int = 1
        self._invalidated_generations: set[int] = set()
        self._task_counter: int = 0

    @property
    def current_generation(self) -> int:
        return self._current_generation

    def reset(self) -> None:
        """Reset task manager state for testing or clean restarts."""
        self._tasks.clear()
        self._current_generation = 1
        self._invalidated_generations.clear()
        self._task_counter = 0

    def next_generation(self) -> int:
        """Increment generation, invalidating all previous tasks."""
        self.invalidate_generation(self._current_generation)
        self._current_generation += 1
        return self._current_generation

    def invalidate_generation(self, generation: int | None = None) -> int:
        """Explicitly invalidate a generation (e.g. on barge-in or correction)."""
        target_gen = generation if generation is not None else self._current_generation
        self._invalidated_generations.add(target_gen)
        # Cancel and mark stale all tasks belonging to this generation or earlier
        cancelled_count = 0
        for task in self._tasks.values():
            if task.generation <= target_gen and task.status in {"pending", "running"}:
                task.mark_stale()
                cancelled_count += 1
        logger.info(
            "invalidated generation %d and cancelled %d active tasks", target_gen, cancelled_count
        )
        if generation is None:
            self._current_generation += 1
        return self._current_generation

    def is_generation_valid(self, generation: int) -> bool:
        """Check if a generation ID is still valid."""
        return generation not in self._invalidated_generations

    def create_task(
        self,
        intent: str,
        total_steps: int = 1,
        parent_task_id: str | None = None,
        generation: int | None = None,
        goal: str = "",
        task_id: str | None = None,
    ) -> AgentTask:
        """Create and register a new tracked agent task."""
        self._task_counter += 1
        gen = generation if generation is not None else self._current_generation
        tid = task_id or f"task_{int(time.time())}_{self._task_counter:04d}"
        task = AgentTask(
            task_id=tid,
            generation=gen,
            intent=intent,
            goal=goal or intent,
            total_steps=total_steps,
            parent_task_id=parent_task_id,
        )
        self._tasks[tid] = task
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        """Check whether a task is cancelled."""
        task = self._tasks.get(task_id)
        if task:
            return task.is_cancelled()
        return True

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None) -> bool:
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if task:
            task.complete(result or {})
            return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task by ID."""
        task = self._tasks.get(task_id)
        if task:
            task.cancel()
            return True
        return False

    def cancel_all_active(self) -> int:
        """Cancel all in-flight tasks (e.g. on voice barge-in or user stop)."""
        count = 0
        for task in self._tasks.values():
            if task.status in {"pending", "running"}:
                task.cancel()
                count += 1
        return count


# Global singleton task manager
default_task_manager = TaskManager()
