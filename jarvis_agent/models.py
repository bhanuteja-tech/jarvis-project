"""Data models for remote action protocol between Jarvis backend and jarvis_agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ActionRequest:
    """Action request received from Jarvis backend."""

    action_id: str
    session_id: str
    step_id: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    timeout_seconds: float = 30.0
    confirmation_timeout_seconds: float = 120.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionRequest:
        payload = data.get("data") if "data" in data and isinstance(data["data"], dict) else data
        return cls(
            action_id=payload.get("action_id", ""),
            session_id=payload.get("session_id", ""),
            step_id=payload.get("step_id", ""),
            tool=payload.get("tool", ""),
            params=payload.get("params") or {},
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            confirmation_prompt=payload.get("confirmation_prompt"),
            timeout_seconds=float(payload.get("timeout_seconds", 30.0)),
            confirmation_timeout_seconds=float(
                payload.get("confirmation_timeout_seconds", 120.0)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionResult:
    """Action result emitted to Jarvis backend."""

    action_id: str
    step_id: str
    success: bool
    message: str = ""
    cancelled: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "action_result",
            "action_id": self.action_id,
            "step_id": self.step_id,
            "success": self.success,
            "message": self.message,
            "cancelled": self.cancelled,
            "details": self.details,
            "observation": self.observation,
        }


__all__ = ["ActionRequest", "ActionResult"]
