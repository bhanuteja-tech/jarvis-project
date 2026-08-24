"""Lightweight LLMOps trace recorder (Phase 12).

A bounded in-memory ring of SAFE routing/runtime events per session:
event type, run/session ids, provider+model names, latency/duration/token
counts, tool names, error codes. Never prompts, never resume text, never
credentials. Optional Opik integration would live behind the same
`record()` interface later; running without it is the default.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX_TRACES = 500

#: Envelope types worth tracing (everything else is chat noise).
TRACED_TYPES = frozenset(
    {
        "agent_started",
        "workflow_node_started",
        "workflow_node_completed",
        "llm_provider_selected",
        "llm_fallback",
        "tool_completed",
        "assistant_message",
        "error",
        "cancelled",
    }
)


class TraceRecorder:
    def __init__(self, max_traces: int = _MAX_TRACES) -> None:
        self._lock = threading.Lock()
        self._ring: deque[dict[str, Any]] = deque(maxlen=max_traces)
        self._counters: dict[str, int] = {
            "llm_calls": 0,
            "tokens_streamed": 0,
            "fallbacks": 0,
            "errors": 0,
            "runs": 0,
        }

    def record_envelope(
        self,
        envelope: dict[str, Any],
        *,
        session_id: str,
        duration_ms: float | None = None,
    ) -> None:
        etype = envelope.get("type")
        if etype not in TRACED_TYPES:
            return
        data = envelope.get("data") or {}
        entry: dict[str, Any] = {
            "ts": time.time(),
            "type": etype,
            "seq": envelope.get("seq"),
            "run_id": envelope.get("run_id"),
            "session_id": session_id,
        }
        for key in ("provider", "model", "code", "node", "from", "to", "action"):
            value = data.get(key)
            if isinstance(value, (str, int, float)):
                entry[key] = value
        if etype == "assistant_message":
            meta = next(
                (
                    a
                    for a in data.get("attachments", [])
                    if isinstance(a, dict) and a.get("kind") == "llm_meta"
                ),
                None,
            )
            if meta:
                entry["provider"] = meta.get("provider")
                entry["model"] = meta.get("model")
                entry["duration_ms"] = meta.get("duration_ms")
                entry["tokens"] = meta.get("tokens")
                self._bump("llm_calls")
                if meta.get("tokens"):
                    self._add("tokens_streamed", int(meta["tokens"]))
            if duration_ms is not None:
                entry["ws_duration_ms"] = round(duration_ms, 1)
        if etype == "token":
            self._add("tokens_streamed", 1)
        if etype == "llm_fallback":
            self._bump("fallbacks")
        if etype == "agent_started":
            self._bump("runs")
        if etype == "error":
            self._bump("errors")

        with self._lock:
            self._ring.append(entry)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._ring)[-limit:]
        return list(reversed(items))  # newest first

    def counters(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def _bump(self, key: str) -> None:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1

    def _add(self, key: str, amount: int) -> None:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount


trace_recorder = TraceRecorder()

__all__ = ["TraceRecorder", "trace_recorder"]
