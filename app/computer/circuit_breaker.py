"""Action Circuit Breaker for JARVIS Computer Control.

Protects against repeated-action infinite loops, zero-progress stalls, and runaway tool calls.

Guarantees:
1. Fingerprints every action: hash(tool_name + normalized_arguments + environment_identity)
2. Detects identical actions: max 2 identical actions without meaningful state change.
3. Detects zero progress: max 3 no-progress steps.
4. Hard bounds: max actions per task (default 30), max task timeout (default 60s).
5. Truthful failure message: 'I couldn't complete that because the computer state stopped changing.'
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerStatus:
    tripped: bool = False
    reason: str = ""
    action_count: int = 0
    identical_action_count: int = 0
    no_progress_count: int = 0


class ActionCircuitBreaker:
    """Task-scoped action circuit breaker tracking progress and repeated actions."""

    def __init__(
        self,
        max_actions: int = 30,
        max_identical_actions: int = 2,
        max_no_progress_steps: int = 3,
        max_retries_per_action: int = 2,
        task_timeout_seconds: float = 60.0,
    ) -> None:
        self.max_actions = max_actions
        self.max_identical_actions = max_identical_actions
        self.max_no_progress_steps = max_no_progress_steps
        self.max_retries_per_action = max_retries_per_action
        self.task_timeout_seconds = task_timeout_seconds

        self.start_time: float = time.perf_counter()
        self.total_action_count: int = 0
        self.last_action_fingerprint: str | None = None
        self.same_action_count: int = 0
        self.last_observation_hash: str | None = None
        self.no_progress_count: int = 0
        self.action_retries: dict[str, int] = {}
        self.tripped: bool = False
        self.trip_reason: str = ""

    def reset_for_task(self, task_timeout_seconds: float | None = None) -> None:
        """Reset circuit breaker counters and timer for a new task execution."""
        if task_timeout_seconds is not None:
            self.task_timeout_seconds = task_timeout_seconds
        self.start_time = time.perf_counter()
        self.tripped = False
        self.trip_reason = ""
        self.total_action_count = 0
        self.same_action_count = 0
        self.last_action_fingerprint = None
        self.last_observation_hash = None
        self.no_progress_count = 0
        self.action_retries.clear()

    def compute_fingerprint(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        environment_identity: str = "",
    ) -> str:
        """Create deterministic SHA-256 fingerprint for tool + args + environment."""
        normalized_args = json.dumps(arguments, sort_keys=True, default=str)
        raw = (
            f"{tool_name.strip().lower()}|"
            f"{normalized_args}|"
            f"{environment_identity.strip().lower()}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def compute_observation_hash(self, observation: dict[str, Any] | Any) -> str:
        """Hash salient observation fields to detect meaningful state change."""
        if hasattr(observation, "to_dict"):
            obs_dict = observation.to_dict()
        elif isinstance(observation, dict):
            obs_dict = observation
        else:
            obs_dict = {"raw": str(observation)}

        # Extract state markers that indicate real progress
        win_title = obs_dict.get("active_window_title") or (
            obs_dict.get("window") or {}
        ).get("title")
        salient = {
            "active_app": obs_dict.get("active_application"),
            "window_title": win_title,
            "url": obs_dict.get("current_url") or (obs_dict.get("browser") or {}).get("url"),
            "directory": obs_dict.get("current_directory"),
            "focused": obs_dict.get("focused_element"),
        }
        raw = json.dumps(salient, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_pre_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        environment_identity: str = "",
    ) -> CircuitBreakerStatus:
        """Validate if the upcoming action violates circuit breaker rules before execution."""
        if self.tripped:
            return CircuitBreakerStatus(tripped=True, reason=self.trip_reason)

        # 1. Check timeout
        elapsed = time.perf_counter() - self.start_time
        if elapsed > self.task_timeout_seconds:
            self.tripped = True
            self.trip_reason = (
                f"Task timed out after {elapsed:.1f}s (limit {self.task_timeout_seconds}s)."
            )
            logger.warning("Circuit breaker tripped: %s", self.trip_reason)
            return CircuitBreakerStatus(tripped=True, reason=self.trip_reason)

        # 2. Check total actions limit
        if self.total_action_count >= self.max_actions:
            self.tripped = True
            self.trip_reason = (
                f"Task exceeded maximum action limit ({self.max_actions} actions)."
            )
            logger.warning("Circuit breaker tripped: %s", self.trip_reason)
            return CircuitBreakerStatus(tripped=True, reason=self.trip_reason)

        # 3. Check identical action repeats
        fingerprint = self.compute_fingerprint(tool_name, arguments, environment_identity)
        if fingerprint == self.last_action_fingerprint:
            if self.same_action_count >= self.max_identical_actions:
                self.tripped = True
                self.trip_reason = (
                    "I couldn't complete that because the computer state stopped changing "
                    f"(action '{tool_name}' repeated {self.same_action_count} times "
                    "without progress)."
                )
                logger.warning("Circuit breaker tripped: %s", self.trip_reason)
                return CircuitBreakerStatus(
                    tripped=True,
                    reason=self.trip_reason,
                    identical_action_count=self.same_action_count,
                )
        return CircuitBreakerStatus(tripped=False)

    def record_action_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        observation: dict[str, Any] | Any,
        verified: bool,
        environment_identity: str = "",
    ) -> CircuitBreakerStatus:
        """Update circuit breaker state after tool execution and observation."""
        self.total_action_count += 1
        fingerprint = self.compute_fingerprint(tool_name, arguments, environment_identity)
        obs_hash = self.compute_observation_hash(observation)

        # Track identical action count
        if fingerprint == self.last_action_fingerprint:
            self.same_action_count += 1
        else:
            self.last_action_fingerprint = fingerprint
            self.same_action_count = 1

        # Track retries per tool
        current_retries = self.action_retries.get(tool_name, 0)
        if not verified:
            self.action_retries[tool_name] = current_retries + 1
        else:
            self.action_retries[tool_name] = 0

        # Check progress detection
        obs_changed = (
            self.last_observation_hash is not None and obs_hash != self.last_observation_hash
        )
        state_changed = obs_changed or verified
        self.last_observation_hash = obs_hash

        if not state_changed:
            self.no_progress_count += 1
        else:
            self.no_progress_count = 0

        # Check triggers
        if self.same_action_count > self.max_identical_actions and not state_changed:
            self.tripped = True
            self.trip_reason = (
                "I couldn't complete that because the computer state stopped changing "
                f"(identical action '{tool_name}' attempted {self.same_action_count} times)."
            )
        elif self.no_progress_count >= self.max_no_progress_steps:
            self.tripped = True
            self.trip_reason = (
                "I couldn't complete that because the computer state stopped changing "
                f"after {self.no_progress_count} steps without detected progress."
            )
        elif self.action_retries.get(tool_name, 0) > self.max_retries_per_action:
            self.tripped = True
            self.trip_reason = (
                f"Action '{tool_name}' failed verification {self.action_retries[tool_name]} times."
            )

        if self.tripped:
            logger.warning("Circuit breaker tripped: %s", self.trip_reason)

        return CircuitBreakerStatus(
            tripped=self.tripped,
            reason=self.trip_reason,
            action_count=self.total_action_count,
            identical_action_count=self.same_action_count,
            no_progress_count=self.no_progress_count,
        )


__all__ = ["ActionCircuitBreaker", "CircuitBreakerStatus"]
