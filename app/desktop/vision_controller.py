"""Vision Controller for visual inspection and element analysis."""

from __future__ import annotations

import logging
from typing import Any

from app.desktop.screen_observer import ScreenObserver, default_screen_observer
from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)


class VisionController:
    """Provides visual understanding of the screen and UI layout."""

    def __init__(
        self,
        screen_observer: ScreenObserver | None = None,
        window_controller: WindowController | None = None,
    ) -> None:
        self.screen_observer = screen_observer or default_screen_observer
        self.window_controller = window_controller or default_window_controller

    def analyze_screen(self) -> dict[str, Any]:
        """Capture screenshot and analyze active UI elements."""
        shot_res = self.screen_observer.capture_screen()
        active_win = self.window_controller.get_active_window()
        win_title = active_win.get("title") if active_win else "Desktop"
        return {
            "success": shot_res.get("success", False),
            "screenshot": shot_res.get("path"),
            "active_window": active_win.get("title") if active_win else None,
            "message": f"Screen analyzed. Active window: {win_title}",
        }

    def answer_visual_question(self, question: str) -> dict[str, Any]:
        """Answer a question about the current visual display."""
        active_win = self.window_controller.get_active_window()
        win_title = active_win.get("title") if active_win else "Desktop"
        return {
            "success": True,
            "question": question,
            "visible_application": win_title,
            "message": f"Looking at your screen, the active window is {win_title}.",
        }


default_vision_controller = VisionController()

__all__ = ["VisionController", "default_vision_controller"]
