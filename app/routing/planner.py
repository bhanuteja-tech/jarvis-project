"""Multi-Action Execution Planner for JARVIS.

Decomposes compound user instructions (e.g. "navigate to desktop and search for vscode",
"open chrome, go to youtube, and search campus x") into discrete sequential steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.routing.taxonomy import Intent


@dataclass(frozen=True)
class PlannedStep:
    """A discrete single action in an execution plan."""

    step_index: int
    intent: Intent
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "intent": str(self.intent),
            "params": self.params,
            "description": self.description,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    """Sequential plan of execution steps."""

    original_text: str
    steps: list[PlannedStep]
    is_compound: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_text": self.original_text,
            "steps": [s.to_dict() for s in self.steps],
            "is_compound": self.is_compound,
        }


class ExecutionPlanner:
    """Decomposes compound sentences into sequential planned steps."""

    def plan(self, text: str) -> list[str]:
        """Split a compound sentence by coordination markers ('and then', 'then', 'and')."""
        clean = (text or "").strip()
        if not clean:
            return []

        split_pattern = (
            r"(?:,\s*(?:and\s+then|then|and)?\s*(?=(?:open|go\s+to|navigate|visit|search|find|list|show|launch|run|type|close|send|message)\b)"
            r"|\s+(?:and\s+then|then)\s+"
            r"|\s+and\s+(?=(?:open|go\s+to|navigate|visit|search|find|list|show|launch|run|type|close|send|message)\b))"
        )

        raw_parts = re.split(split_pattern, clean, flags=re.IGNORECASE)
        parts = [p.strip().strip(",. ") for p in raw_parts if p.strip().strip(",. ")]

        return parts if len(parts) > 1 else [clean]


# Global planner singleton
default_planner = ExecutionPlanner()
