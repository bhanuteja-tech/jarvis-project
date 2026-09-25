"""Desktop action enums and result dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DesktopAction(StrEnum):
    """Curated set of allowed desktop operations."""

    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    SEARCH_WEB = "search_web"
    OPEN_FILE = "open_file"
    SYSTEM_INFO = "system_info"
    SCREENSHOT = "screenshot"
    TYPE_TEXT = "type_text"
    VOLUME_CONTROL = "volume_control"
    CLOSE_APP = "close_app"
    LIST_RUNNING = "list_running"
    OPEN_SERVICE = "open_service"
    OPEN_BROWSER = "open_browser"
    NAVIGATE_BACK = "navigate_back"
    OPEN_DESKTOP = "open_desktop"
    OPEN_FOLDER = "open_folder"
    LIST_FILES = "list_files"
    OPEN_RESUME = "open_resume"
    FOCUS_APP = "focus_app"


@dataclass(frozen=True)
class ActionResult:
    """Immutable result of a desktop action execution."""

    success: bool
    message: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "action": self.action,
            "details": self.details,
        }


__all__ = ["ActionResult", "DesktopAction"]
