"""Window Controller for inspecting, enumerating, and focusing application windows.

Uses Windows user32 API via ctypes with defensive error handling,
interactive desktop station attachment, and reliable foreground window switching.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system().lower() == "windows"

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
else:
    user32 = None
    kernel32 = None


def attach_to_default_desktop() -> None:
    """Attach the calling thread to the interactive user desktop if running on Windows."""
    if not IS_WINDOWS or user32 is None:
        return
    try:
        # DESKTOP_ALL_ACCESS = 0x01FF
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as exc:  # noqa: BLE001
        logger.debug("attach_to_default_desktop error: %s", exc)


class WindowController:
    """Controls OS windows, retrieves active window, and handles focus."""

    def list_windows(self) -> list[dict[str, Any]]:
        """List all visible top-level windows from the interactive desktop."""
        if not IS_WINDOWS or user32 is None:
            return []

        attach_to_default_desktop()
        windows: list[dict[str, Any]] = []

        def enum_windows_callback(hwnd: int, lparam: Any) -> bool:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    # Filter out empty or common hidden overlay windows
                    if title and title not in {"Program Manager", "Settings"}:
                        pid = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        windows.append(
                            {
                                "window_id": str(hwnd),
                                "hwnd": hwnd,
                                "title": title,
                                "pid": pid.value,
                            }
                        )
            return True

        cb = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(cb, 0)
        return windows

    def list_open_windows(self) -> list[dict[str, Any]]:
        """Alias for list_windows to maintain backward compatibility."""
        return self.list_windows()

    def get_active_window(self) -> dict[str, Any] | None:
        """Get information about the currently focused foreground window."""
        if not IS_WINDOWS or user32 is None:
            return None

        attach_to_default_desktop()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        return {
            "window_id": str(hwnd),
            "hwnd": hwnd,
            "title": title,
            "pid": pid.value,
        }

    def get_window_title(self, hwnd: int) -> str:
        """Get window title by handle."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value.strip()
        return ""

    def get_process_id(self, hwnd: int) -> int | None:
        """Get process ID for window handle."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def get_bounds(self, hwnd: int) -> dict[str, int] | None:
        """Get bounding rectangle coordinates (left, top, right, bottom, width, height)."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            }
        return None

    def get_window_bounds(self, hwnd: int) -> dict[str, int] | None:
        """Alias for get_bounds."""
        return self.get_bounds(hwnd)

    def is_window_visible(self, hwnd: int) -> bool:
        """Check if window handle is visible."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return False
        return bool(user32.IsWindowVisible(hwnd))

    def is_window_active(self, hwnd: int) -> bool:
        """Check if target window is currently the foreground active window."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return False
        attach_to_default_desktop()
        return int(user32.GetForegroundWindow()) == int(hwnd)

    def find_window(
        self,
        pattern_or_title: str,
        app_canonical: str | None = None,
    ) -> dict[str, Any] | None:
        """Find the first window matching a title substring, regex pattern, or process name."""
        attach_to_default_desktop()
        regex = re.compile(pattern_or_title, re.IGNORECASE)

        # First check windows by title
        open_wins = self.list_windows()
        for win in open_wins:
            if regex.search(win["title"]):
                return win

        # Second check: match by process name if app_canonical given
        if app_canonical:
            import psutil

            canonical_lower = app_canonical.lower().replace(" ", "_")
            search_procs = {canonical_lower, f"{canonical_lower}.exe"}
            if "chrome" in canonical_lower:
                search_procs.update({"chrome.exe", "chrome"})
            elif "edge" in canonical_lower:
                search_procs.update({"msedge.exe", "msedge"})
            elif "code" in canonical_lower:
                search_procs.update({"code.exe", "code"})
            elif "explorer" in canonical_lower:
                search_procs.update({"explorer.exe", "explorer"})
            elif "whatsapp" in canonical_lower:
                search_procs.update({"whatsapp.exe", "whatsapp"})

            for win in open_wins:
                pid = win.get("pid")
                if pid:
                    try:
                        p = psutil.Process(pid)
                        if p.name().lower() in search_procs:
                            return win
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

        return None

    def find_window_by_title(self, pattern: str) -> dict[str, Any] | None:
        """Find the first window matching a title substring or regex pattern."""
        return self.find_window(pattern)

    def bring_to_front(self, hwnd: int) -> bool:
        """Bring target window to the foreground using Windows thread input attachment."""
        if not IS_WINDOWS or user32 is None or not hwnd:
            return False

        attach_to_default_desktop()

        try:
            fg_hwnd = user32.GetForegroundWindow()
            cur_thread = kernel32.GetCurrentThreadId() if kernel32 else 0
            fg_thread = (
                user32.GetWindowThreadProcessId(fg_hwnd, None) if (user32 and fg_hwnd) else 0
            )

            attached = False
            if fg_thread and cur_thread and fg_thread != cur_thread:
                attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))

            # If minimized (iconic), restore it (SW_RESTORE = 9), else show (SW_SHOW = 5)
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            else:
                user32.ShowWindow(hwnd, 5)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            # Fallback bypass: synthesize Alt keypress to release foreground lock
            time.sleep(0.06)
            if user32.GetForegroundWindow() != hwnd:
                user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
                user32.SetForegroundWindow(hwnd)
                user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up

            if attached and fg_thread and cur_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, False)

            time.sleep(0.05)
            is_active = user32.GetForegroundWindow() == hwnd
            logger.info("bring_to_front hwnd=%s active=%s", hwnd, is_active)
            return is_active
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not bring window %s to front: %s", hwnd, exc)
            return False

    def focus_window(self, hwnd_or_title: int | str) -> bool:
        """Bring target window to the foreground."""
        if not IS_WINDOWS or user32 is None:
            return False

        hwnd: int | None = None
        if isinstance(hwnd_or_title, int):
            hwnd = hwnd_or_title
        else:
            win = self.find_window_by_title(str(hwnd_or_title))
            if win:
                hwnd = win["hwnd"]

        if hwnd:
            return self.bring_to_front(hwnd)
        return False


default_window_controller = WindowController()

__all__ = ["WindowController", "attach_to_default_desktop", "default_window_controller"]
