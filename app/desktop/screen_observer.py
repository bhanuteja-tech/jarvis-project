"""Screen Observer for capturing screenshots and active window bounds.

Uses PIL.ImageGrab with defensive error handling.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)


class ScreenObserver:
    """Captures desktop screenshots and window viewports."""

    def __init__(self, window_controller: WindowController | None = None) -> None:
        self.window_controller = window_controller or default_window_controller

    def capture_screen(self, output_path: str | None = None) -> dict[str, Any]:
        """Capture full screen image and save to disk."""
        target = (
            Path(output_path)
            if output_path
            else (Path.cwd() / "screenshots" / f"screen_{int(time.time())}.png")
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            img = ImageGrab.grab(all_screens=True)
            img.save(str(target), format="PNG")
            logger.info("screenshot saved to %s", target)
            return {
                "success": True,
                "action": "capture_screen",
                "path": str(target),
                "width": img.width,
                "height": img.height,
                "message": f"Screenshot captured and saved to {target.name}.",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("error capturing screen: %s", exc)
            return {
                "success": False,
                "action": "capture_screen",
                "error": f"Failed to capture screen: {exc}",
            }

    def get_active_window_screenshot(self, output_path: str | None = None) -> dict[str, Any]:
        """Capture only the bounding box of the active window."""
        active_win = self.window_controller.get_active_window()
        if not active_win:
            return self.capture_screen(output_path)

        hwnd = active_win.get("hwnd")
        bounds = self.window_controller.get_window_bounds(hwnd) if hwnd else None
        if not bounds or bounds["width"] <= 0 or bounds["height"] <= 0:
            return self.capture_screen(output_path)

        target = (
            Path(output_path)
            if output_path
            else (Path.cwd() / "screenshots" / f"window_{int(time.time())}.png")
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        bbox = (bounds["left"], bounds["top"], bounds["right"], bounds["bottom"])
        try:
            img = ImageGrab.grab(bbox=bbox)
            img.save(str(target), format="PNG")
            return {
                "success": True,
                "action": "capture_window",
                "path": str(target),
                "window_title": active_win.get("title"),
                "message": f"Captured active window '{active_win.get('title')}'.",
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("error capturing window: %s", exc)
            return self.capture_screen(output_path)


default_screen_observer = ScreenObserver()

__all__ = ["ScreenObserver", "default_screen_observer"]
