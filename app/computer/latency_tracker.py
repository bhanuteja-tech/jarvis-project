"""Latency and Execution Instrumentation Tracker for JARVIS.

Tracks per-request and per-task lifecycle latencies:
- routing_latency
- laya_latency
- model_latency
- tool_latency
- observation_latency
- verification_latency
- tts_latency
- total_latency

Maintains running window statistics (P50, P95, P99, averages, counts, rates)
for the developer observability dashboard.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RequestLatencyTrace:
    """Detailed timestamp and latency trace for a single request/task."""

    request_id: str
    task_id: str
    generation: int
    user_goal: str

    # Timestamps (perf_counter)
    request_received: float = field(default_factory=time.perf_counter)
    routing_start: float | None = None
    routing_end: float | None = None
    laya_start: float | None = None
    laya_end: float | None = None
    llm_start: float | None = None
    llm_first_token: float | None = None
    llm_end: float | None = None
    tool_start: float | None = None
    tool_end: float | None = None
    observation_start: float | None = None
    observation_end: float | None = None
    verification_start: float | None = None
    verification_end: float | None = None
    response_start: float | None = None
    response_end: float | None = None
    tts_start: float | None = None
    tts_end: float | None = None

    # Counts and flags
    system_tier_used: str = "SYSTEM_0"  # SYSTEM_0, SYSTEM_1_LAYA, SYSTEM_2_GEMINI
    action_count: int = 0
    model_call_count: int = 0
    retries_count: int = 0
    circuit_break_triggered: bool = False
    cancelled: bool = False
    success: bool = False

    # Cumulative durations (for multi-step tasks)
    cumulative_tool_duration: float = 0.0
    cumulative_observation_duration: float = 0.0
    cumulative_verification_duration: float = 0.0
    cumulative_model_duration: float = 0.0

    def mark(self, step_name: str) -> None:
        """Convenience method to set timestamp for a named phase."""
        now = time.perf_counter()
        if hasattr(self, step_name):
            setattr(self, step_name, now)
        if step_name == "tool_start":
            self.action_count += 1
        elif step_name == "llm_start":
            self.model_call_count += 1
        elif step_name == "tool_end" and self.tool_start:
            self.cumulative_tool_duration += now - self.tool_start
        elif step_name == "observation_end" and self.observation_start:
            self.cumulative_observation_duration += now - self.observation_start
        elif step_name == "verification_end" and self.verification_start:
            self.cumulative_verification_duration += now - self.verification_start
        elif step_name == "llm_end" and self.llm_start:
            self.cumulative_model_duration += now - self.llm_start

    @property
    def metrics(self) -> RequestLatencyTrace:
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.summary()

    def mark_routing_start(self) -> None:
        self.routing_start = time.perf_counter()

    def mark_routing_end(self) -> None:
        self.routing_end = time.perf_counter()

    def mark_laya_start(self) -> None:
        self.laya_start = time.perf_counter()

    def mark_laya_end(self) -> None:
        self.laya_end = time.perf_counter()

    def mark_llm_start(self) -> None:
        self.llm_start = time.perf_counter()
        self.model_call_count += 1

    def mark_llm_first_token(self) -> None:
        self.llm_first_token = time.perf_counter()

    def mark_llm_end(self) -> None:
        self.llm_end = time.perf_counter()
        if self.llm_start:
            self.cumulative_model_duration += self.llm_end - self.llm_start

    def mark_tool_start(self) -> None:
        self.tool_start = time.perf_counter()
        self.action_count += 1

    def mark_tool_end(self) -> None:
        self.tool_end = time.perf_counter()
        if self.tool_start:
            self.cumulative_tool_duration += self.tool_end - self.tool_start

    def mark_observation_start(self) -> None:
        self.observation_start = time.perf_counter()

    def mark_observation_end(self) -> None:
        self.observation_end = time.perf_counter()
        if self.observation_start:
            self.cumulative_observation_duration += self.observation_end - self.observation_start

    def mark_verification_start(self) -> None:
        self.verification_start = time.perf_counter()

    def mark_verification_end(self) -> None:
        self.verification_end = time.perf_counter()
        if self.verification_start:
            self.cumulative_verification_duration += self.verification_end - self.verification_start

    def mark_response_start(self) -> None:
        self.response_start = time.perf_counter()

    def mark_response_end(self) -> None:
        self.response_end = time.perf_counter()

    def mark_tts_start(self) -> None:
        self.tts_start = time.perf_counter()

    def mark_tts_end(self) -> None:
        self.tts_end = time.perf_counter()

    @property
    def routing_latency(self) -> float:
        if self.routing_start and self.routing_end:
            return max(0.0, self.routing_end - self.routing_start)
        return 0.0

    @property
    def laya_latency(self) -> float:
        if self.laya_start and self.laya_end:
            return max(0.0, self.laya_end - self.laya_start)
        return 0.0

    @property
    def model_latency(self) -> float:
        if self.cumulative_model_duration > 0:
            return max(0.0, self.cumulative_model_duration)
        if self.llm_start and self.llm_end:
            return max(0.0, self.llm_end - self.llm_start)
        return 0.0

    @property
    def tool_latency(self) -> float:
        if self.cumulative_tool_duration > 0:
            return max(0.0, self.cumulative_tool_duration)
        if self.tool_start and self.tool_end:
            return max(0.0, self.tool_end - self.tool_start)
        return 0.0

    @property
    def observation_latency(self) -> float:
        if self.cumulative_observation_duration > 0:
            return max(0.0, self.cumulative_observation_duration)
        if self.observation_start and self.observation_end:
            return max(0.0, self.observation_end - self.observation_start)
        return 0.0

    @property
    def verification_latency(self) -> float:
        if self.cumulative_verification_duration > 0:
            return max(0.0, self.cumulative_verification_duration)
        if self.verification_start and self.verification_end:
            return max(0.0, self.verification_end - self.verification_start)
        return 0.0

    @property
    def tts_latency(self) -> float:
        if self.tts_start and self.tts_end:
            return max(0.0, self.tts_end - self.tts_start)
        return 0.0

    @property
    def response_latency(self) -> float:
        if self.response_start and self.response_end:
            return max(0.0, self.response_end - self.response_start)
        return 0.0

    @property
    def total_latency(self) -> float:
        end_time = self.response_end or self.tts_end or time.perf_counter()
        return max(0.0, end_time - self.request_received)

    def summary(self) -> dict[str, Any]:
        """Produce clean metrics dictionary for WebSocket emission and dashboard."""
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "generation": self.generation,
            "system_tier": self.system_tier_used,
            "action_count": self.action_count,
            "model_call_count": self.model_call_count,
            "routing_latency": round(self.routing_latency, 3),
            "laya_latency": round(self.laya_latency, 3),
            "model_latency": round(self.model_latency, 3),
            "tool_latency": round(self.tool_latency, 3),
            "observation_latency": round(self.observation_latency, 3),
            "verification_latency": round(self.verification_latency, 3),
            "response_latency": round(self.response_latency, 3),
            "tts_latency": round(self.tts_latency, 3),
            "total_latency": round(self.total_latency, 3),
            "circuit_break": self.circuit_break_triggered,
            "cancelled": self.cancelled,
            "success": self.success,
        }


class LatencyTracker:
    """Maintains a rolling window of request latency traces and computes dashboard aggregates."""

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: deque[RequestLatencyTrace] = deque(maxlen=max_history)
        self._active_traces: dict[str, RequestLatencyTrace] = {}

    def start_trace(
        self,
        request_id: str = "",
        task_id: str = "",
        generation: int = 1,
        user_goal: str = "",
        user_request: str = "",
        **kwargs: Any,
    ) -> RequestLatencyTrace:
        import uuid
        goal = user_request or user_goal
        req_id = request_id or f"req_{uuid.uuid4().hex[:8]}"
        trace = RequestLatencyTrace(
            request_id=req_id,
            task_id=task_id,
            generation=generation,
            user_goal=goal,
        )
        self._active_traces[req_id] = trace
        return trace

    def get_trace(self, request_id: str) -> RequestLatencyTrace | None:
        return self._active_traces.get(request_id)

    def complete_trace(self, request_id: str, success: bool = True) -> RequestLatencyTrace | None:
        trace = self._active_traces.pop(request_id, None)
        if trace:
            trace.success = success
            if not trace.response_end:
                trace.mark_response_end()
            self._history.append(trace)
        return trace

    def get_dashboard_metrics(self) -> dict[str, Any]:
        """Calculate P50, P95, P99, averages, and rates for the developer dashboard."""
        if not self._history:
            return {
                "sample_count": 0,
                "avg_total_latency": 0.0,
                "p50_total_latency": 0.0,
                "p95_total_latency": 0.0,
                "p99_total_latency": 0.0,
                "avg_model_latency": 0.0,
                "avg_laya_latency": 0.0,
                "avg_tool_latency": 0.0,
                "avg_observation_latency": 0.0,
                "avg_verification_latency": 0.0,
                "avg_tts_latency": 0.0,
                "avg_actions_per_task": 0.0,
                "avg_model_calls_per_task": 0.0,
                "task_completion_rate": 1.0,
                "cancellation_rate": 0.0,
                "circuit_break_rate": 0.0,
            }

        totals = sorted(t.total_latency for t in self._history)
        count = len(totals)

        def percentile(p: float) -> float:
            k = (len(totals) - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return totals[int(k)]
            d0 = totals[int(f)] * (c - k)
            d1 = totals[int(c)] * (k - f)
            return d0 + d1

        p50 = percentile(0.50)
        p95 = percentile(0.95)
        p99 = percentile(0.99)
        avg_total = sum(totals) / count

        avg_model = sum(t.model_latency for t in self._history) / count
        avg_laya = sum(t.laya_latency for t in self._history) / count
        avg_tool = sum(t.tool_latency for t in self._history) / count
        avg_obs = sum(t.observation_latency for t in self._history) / count
        avg_verif = sum(t.verification_latency for t in self._history) / count
        avg_tts = sum(t.tts_latency for t in self._history) / count

        avg_actions = sum(t.action_count for t in self._history) / count
        avg_calls = sum(t.model_call_count for t in self._history) / count

        successful = sum(1 for t in self._history if t.success)
        cancelled = sum(1 for t in self._history if t.cancelled)
        circuit_broken = sum(1 for t in self._history if t.circuit_break_triggered)

        return {
            "sample_count": count,
            "avg_total_latency": round(avg_total, 3),
            "p50_total_latency": round(p50, 3),
            "p95_total_latency": round(p95, 3),
            "p99_total_latency": round(p99, 3),
            "avg_model_latency": round(avg_model, 3),
            "avg_laya_latency": round(avg_laya, 3),
            "avg_tool_latency": round(avg_tool, 3),
            "avg_observation_latency": round(avg_obs, 3),
            "avg_verification_latency": round(avg_verif, 3),
            "avg_tts_latency": round(avg_tts, 3),
            "avg_actions_per_task": round(avg_actions, 2),
            "avg_model_calls_per_task": round(avg_calls, 2),
            "task_completion_rate": round(successful / count, 3),
            "cancellation_rate": round(cancelled / count, 3),
            "circuit_break_rate": round(circuit_broken / count, 3),
        }


# Global singleton tracker for cross-task dashboard aggregation
global_latency_tracker = LatencyTracker()

__all__ = [
    "RequestLatencyTrace",
    "LatencyTracker",
    "global_latency_tracker",
]
