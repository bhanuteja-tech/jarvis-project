"""Canonical ComputerObservation model for JARVIS Computer Control.

Represents REAL observed current state gathered from OS APIs, user32,
filesystem inspection, window controllers, and browser sessions.

Never fabricates missing fields.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ComputerObservation:
    """Canonical observation of current computer environment."""

    timestamp: float = field(default_factory=time.time)
    active_application: str | None = None
    active_window: dict[str, Any] | None = None
    browser: str | None = None
    browser_tabs: list[dict[str, Any]] = field(default_factory=list)
    current_url: str | None = None
    page_title: str | None = None
    directory: str | None = None
    filesystem_items: list[dict[str, Any]] = field(default_factory=list)
    screenshot_id: str | None = None
    DOM_snapshot: dict[str, Any] | None = None
    accessibility_snapshot: list[dict[str, Any]] = field(default_factory=list)
    focused_element: str | None = None
    visible_text: str | None = None

    # Auxiliary metadata
    open_windows: list[dict[str, Any]] = field(default_factory=list)
    running_processes_count: int | None = None
    active_window_title: str | None = None

    def __post_init__(self) -> None:
        if not self.active_window_title and self.active_window:
            self.active_window_title = self.active_window.get("title")

    def to_dict(self) -> dict[str, Any]:
        """Convert observation to dictionary, omitting None values where appropriate."""
        data = asdict(self)
        # Ensure active_window_title is present for backward compatibility
        if not data.get("active_window_title") and data.get("active_window"):
            data["active_window_title"] = (data.get("active_window") or {}).get("title")
        return data

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access for backward compatibility with existing callers."""
        d = self.to_dict()
        return d.get(key, default)


__all__ = ["ComputerObservation"]
