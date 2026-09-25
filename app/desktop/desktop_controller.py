"""Desktop Controller for opening File Explorer to Desktop, Downloads, and custom directories.

Maintains authoritative directory context in ComputerState so follow-up commands
(such as 'what files are available?' or 'open my resume') inspect the exact active directory.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.desktop.state import ComputerState, default_computer_state
from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)


def get_actual_desktop_path() -> Path:
    """Detect actual user Desktop path, respecting OneDrive sync if active."""
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.is_dir():
        return onedrive_desktop
    std_desktop = Path.home() / "Desktop"
    if std_desktop.is_dir():
        return std_desktop
    return Path.home()


def resolve_folder_path(target: str, parent: str | None = None) -> Path | None:
    """Resolve human folder name (e.g. 'downloads', 'documents', 'desktop', 'music') to a Path."""
    cleaned = target.strip().lower()
    # Strip common suffixes like "folder" or "directory"
    import re
    cleaned = re.sub(r"\b(?:folder|directory)\b", "", cleaned).strip()

    desktop_path = get_actual_desktop_path()

    # If parent is explicitly Desktop or target is "desktop/child"
    if "/" in cleaned or "\\" in cleaned:
        parts = re.split(r"[/\\]", cleaned)
        parent_name = parts[0].strip()
        child_name = parts[1].strip()
        if parent_name == "desktop":
            cand = desktop_path / child_name
            if cand.is_dir():
                return cand.resolve()

    if parent and parent.lower() == "desktop":
        cand = desktop_path / cleaned.capitalize()
        if cand.is_dir():
            return cand.resolve()
        cand_lower = desktop_path / cleaned
        if cand_lower.is_dir():
            return cand_lower.resolve()

    if cleaned in {"desktop", "the desktop", "my desktop"}:
        return desktop_path
    if cleaned in {"downloads", "the downloads", "my downloads"}:
        p = Path.home() / "Downloads"
        return p if p.is_dir() else None
    if cleaned in {"documents", "the documents", "my documents"}:
        p = Path.home() / "Documents"
        return p if p.is_dir() else None
    if cleaned in {"music", "my music"}:
        # Check Desktop/Music first, then user Music folder
        desk_music = desktop_path / "Music"
        if desk_music.is_dir():
            return desk_music.resolve()
        p = Path.home() / "Music"
        return p if p.is_dir() else None
    if cleaned in {"videos", "my videos"}:
        p = Path.home() / "Videos"
        return p if p.is_dir() else None
    if cleaned in {"pictures", "my pictures"}:
        p = Path.home() / "Pictures"
        return p if p.is_dir() else None

    # Check under Desktop
    desk_child = desktop_path / cleaned.capitalize()
    if desk_child.is_dir():
        return desk_child.resolve()

    # Check under user home
    home_child = Path.home() / cleaned.capitalize()
    if home_child.is_dir():
        return home_child.resolve()

    # Try direct path
    cand = Path(target)
    if cand.is_dir():
        return cand.resolve()
    return None


class DesktopController:
    """Controls opening folders, Desktop, and updating the filesystem context."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state

    def resolve_folder_path(self, target: str, parent: str | None = None) -> Path | None:
        """Resolve folder path with optional parent directory constraint."""
        return resolve_folder_path(target, parent=parent)

    def open_desktop(self) -> dict[str, Any]:
        """Open Windows File Explorer to the user's Desktop."""
        desktop_path = get_actual_desktop_path()
        return self.open_folder(str(desktop_path), display_name="Desktop")

    def open_folder(
        self, folder_path_or_name: str, display_name: str | None = None, parent: str | None = None
    ) -> dict[str, Any]:
        """Open Windows File Explorer to target folder, verify window, and update state."""
        resolved = resolve_folder_path(folder_path_or_name, parent=parent)
        if not resolved or not resolved.is_dir():
            return {
                "success": False,
                "action": "open_folder",
                "target": folder_path_or_name,
                "error": f"Folder '{folder_path_or_name}' does not exist on this machine.",
            }

        name = display_name or resolved.name or "Folder"

        # Launch File Explorer targeted to this path
        try:
            os.startfile(str(resolved))
        except Exception as exc:  # noqa: BLE001
            try:
                subprocess.Popen(["explorer.exe", str(resolved)])
            except Exception as shell_exc:  # noqa: BLE001
                return {
                    "success": False,
                    "action": "open_folder",
                    "target": str(resolved),
                    "error": f"Failed to open explorer for {resolved}: {exc} / {shell_exc}",
                }

        # Verify Explorer window or focus
        time.sleep(0.4)
        win = self.window_controller.find_window_by_title(name)
        if not win:
            win = self.window_controller.find_window_by_title("explorer")
        if win:
            self.window_controller.focus_window(win["hwnd"])

        # Update computer state with authoritative filesystem context
        self.state.update(
            active_application="File Explorer",
            active_window_id=win["window_id"] if win else None,
            active_window_title=win["title"] if win else f"File Explorer - {name}",
            current_directory=str(resolved),
            last_action="open_folder",
        )

        # Deactivate active web context so File Explorer state is authoritative
        if hasattr(self.state, "web_context") and self.state.web_context:
            self.state.web_context.page = None
            self.state.web_context.current_list.clear()
            self.state.web_context.ordinal_basis = None

        logger.info("updated computer state: current_directory=%s", resolved)
        return {
            "success": True,
            "action": "open_folder",
            "folder": name,
            "directory": str(resolved),
            "window_id": win["window_id"] if win else None,
            "message": f"{name} is open. What would you like me to do?",
        }

    def get_current_directory(self) -> str:
        """Get the current authoritative directory."""
        return self.state.current_directory


default_desktop_controller = DesktopController()

__all__ = ["DesktopController", "default_desktop_controller", "get_actual_desktop_path"]
