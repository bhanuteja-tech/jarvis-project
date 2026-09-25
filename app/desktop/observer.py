"""Computer Observer Service for JARVIS.

Inspects actual Windows OS state: active window, running processes,
file explorer location, browser URL, screen state, and UI accessibility trees.
Ensures zero hallucination by reporting only ground truth from the operating system.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.desktop.screen_observer import ScreenObserver, default_screen_observer
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.ui_automation import default_ui_automation
from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)


class ComputerObserver:
    """Observes and snapshots the state of the user's computer."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        screen_observer: ScreenObserver | None = None,
        state: ComputerState | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.screen_observer = screen_observer or default_screen_observer
        self.state = state or default_computer_state

    def observe_active_window(self) -> dict[str, Any] | None:
        """Query user32 for the foreground window with visibility and active status."""
        active = self.window_controller.get_active_window()
        if not active:
            return None

        hwnd = active.get("hwnd")
        is_visible = self.window_controller.is_window_visible(hwnd) if hwnd else False
        is_active = self.window_controller.is_window_active(hwnd) if hwnd else False

        return {
            "id": active.get("window_id"),
            "hwnd": hwnd,
            "title": active.get("title", ""),
            "pid": active.get("pid"),
            "visible": is_visible,
            "foreground": is_active,
        }

    def observe_application(self) -> dict[str, Any]:
        """Inspect the current active application and underlying process."""
        active_win = self.observe_active_window()
        app_name = "Unknown"
        if active_win:
            title = active_win.get("title", "")
            if "visual studio code" in title.lower() or " - code" in title.lower():
                app_name = "Visual Studio Code"
            elif "chrome" in title.lower():
                app_name = "Google Chrome"
            elif "edge" in title.lower():
                app_name = "Microsoft Edge"
            elif "whatsapp" in title.lower():
                app_name = "WhatsApp"
            elif "explorer" in title.lower() or "desktop" in title.lower():
                app_name = "File Explorer"
            else:
                app_name = title.split(" - ")[-1].strip() if " - " in title else title

        return {
            "active_application": app_name,
            "window": active_win,
            "active_process": self.state.active_process,
        }

    def observe_browser(self) -> dict[str, Any]:
        """Return structured browser session and active page observation."""
        return {
            "name": self.state.browser_name or self.state.browser,
            "window_id": self.state.browser_window_id,
            "context_id": self.state.browser_context_id,
            "active_page_id": self.state.active_page_id,
            "url": self.state.active_page_url or self.state.current_url,
            "title": self.state.active_page_title or self.state.active_tab,
            "open_pages_count": len(self.state.open_pages),
            "open_pages": list(self.state.open_pages),
        }

    def observe_filesystem(self) -> dict[str, Any]:
        """Return authoritative current directory and recent search results."""
        return {
            "current_directory": self.state.current_directory,
            "selected_file": self.state.selected_file,
            "last_search_results": list(self.state.last_search_results),
            "open_files": list(self.state.open_files),
        }

    def capture_screen(self) -> dict[str, Any]:
        """Capture screenshot."""
        return self.screen_observer.capture_screen()

    def observe_ui_tree(self, hwnd: int | None = None) -> list[dict[str, Any]]:
        """Inspect visible UI accessibility controls for target or active window."""
        target_hwnd = hwnd
        if not target_hwnd:
            active = self.window_controller.get_active_window()
            if active:
                target_hwnd = active.get("hwnd")
        if not target_hwnd:
            return []
        return default_ui_automation.inspect_window_tree(target_hwnd, max_depth=2)

    def get_open_windows(self) -> list[dict[str, Any]]:
        """Enumerate visible desktop application windows."""
        return self.window_controller.list_open_windows()

    def get_running_applications(self) -> list[dict[str, Any]]:
        """List distinct running application processes."""
        import psutil

        apps: list[dict[str, Any]] = []
        seen: set[str] = set()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name")
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                apps.append({"pid": proc.info.get("pid"), "name": name})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return apps

    def get_current_directory(self) -> str:
        """Return the authoritative current working / explorer directory."""
        return self.state.current_directory

    def get_browser_state(self) -> dict[str, Any]:
        """Return current browser context (backward compatible alias)."""
        return self.observe_browser()

    def get_active_window(self) -> dict[str, Any] | None:
        """Backward compatible alias for observe_active_window."""
        return self.observe_active_window()

    def observe(self) -> dict[str, Any]:
        """Produce an authoritative structured snapshot of the computer environment."""
        app_obs = self.observe_application()
        active_win = app_obs.get("window")
        browser_info = self.observe_browser()
        fs_info = self.observe_filesystem()
        open_wins = self.get_open_windows()

        observation = {
            "timestamp": time.time(),
            "active_application": (
                app_obs.get("active_application") or self.state.active_application
            ),
            "window": active_win,
            "active_window_id": active_win.get("id") if active_win else self.state.active_window_id,
            "active_window_title": (
                active_win.get("title") if active_win else self.state.active_window_title
            ),
            "browser": browser_info,
            "filesystem": fs_info,
            "current_directory": self.state.current_directory,
            "open_windows_count": len(open_wins),
        }

        # Update ComputerState observation cache
        self.state.last_observation = (
            f"{observation['active_application']} is in the foreground"
        )
        return observation


# Global singleton observer
default_observer = ComputerObserver()

__all__ = ["ComputerObserver", "default_observer"]
