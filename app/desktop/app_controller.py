"""Application Controller for launching, monitoring, focusing, and terminating desktop applications.

Includes real OS process inspection and window verification — never assumes success.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

import psutil

from app.desktop.observer import ComputerObserver, default_observer
from app.desktop.safety import CLOSEABLE_APPS
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.verifier import VerificationService, default_verifier
from app.desktop.window_controller import WindowController, default_window_controller
from app.routing.app_resolver import ApplicationResolver, default_app_resolver

logger = logging.getLogger(__name__)


class ApplicationController:
    """Controls OS application processes with verification and window tracking."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
        app_resolver: ApplicationResolver | None = None,
        verifier: VerificationService | None = None,
        observer: ComputerObserver | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state
        self.app_resolver = app_resolver or default_app_resolver
        self.verifier = verifier or default_verifier
        self.observer = observer or default_observer

    def is_application_running(self, app_name: str) -> tuple[bool, int | None]:
        """Check whether an application is currently running by process name."""
        canonical = self.app_resolver.canonicalize(app_name) or app_name.strip().lower()
        search_terms = {canonical, f"{canonical}.exe"}
        if canonical in {"google_chrome", "chrome"}:
            search_terms.update({"chrome.exe", "chrome"})
        elif canonical in {"microsoft_edge", "edge", "msedge"}:
            search_terms.update({"msedge.exe", "msedge"})
        elif canonical in {"visual_studio_code", "vscode", "code"}:
            search_terms.update({"code.exe", "code"})
        elif canonical in {"file_explorer", "explorer"}:
            search_terms.update({"explorer.exe", "explorer"})

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = (proc.info["name"] or "").lower()
                if pname in search_terms:
                    return True, proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False, None

    def get_active_application(self) -> dict[str, Any] | None:
        """Inspect the currently focused window and its underlying process."""
        active_win = self.window_controller.get_active_window()
        if not active_win:
            return None

        pid = active_win.get("pid")
        proc_name = "Unknown"
        if pid:
            try:
                p = psutil.Process(pid)
                proc_name = p.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return {
            "application": proc_name,
            "window_id": active_win.get("window_id"),
            "window_title": active_win.get("title"),
            "pid": pid,
        }

    def open_application(self, app_name: str, *, args: list[str] | None = None) -> dict[str, Any]:
        """Launch or focus an application, verify it opened, and update state."""
        raw_name = app_name.strip()
        resolved = self.app_resolver.resolve(raw_name)
        if not resolved:
            return {
                "success": False,
                "action": "open_application",
                "application": raw_name,
                "error": f"Application '{raw_name}' could not be located on this machine.",
                "message": f"I couldn't open {raw_name}. I couldn't locate the application.",
            }

        display = resolved.display_name
        canonical = resolved.canonical_name

        # 1. If application is already running and has a visible window, focus it!
        win = self.window_controller.find_window(display, app_canonical=canonical)
        if not win:
            win = self.window_controller.find_window(
                canonical.replace("_", " "), app_canonical=canonical
            )
        if not win and canonical == "visual_studio_code":
            win = self.window_controller.find_window("code", app_canonical=canonical)
        if not win and canonical == "google_chrome":
            win = self.window_controller.find_window("chrome", app_canonical=canonical)
        if not win and canonical == "microsoft_edge":
            win = self.window_controller.find_window("edge", app_canonical=canonical)
        if not win and canonical == "file_explorer":
            win = self.window_controller.find_window("explorer", app_canonical=canonical)

        if win:
            focused = self.window_controller.bring_to_front(win["hwnd"])
            self.state.update(
                active_application=display,
                active_process=f"{canonical}.exe",
                active_window_id=win["window_id"],
                active_window_title=win["title"],
                last_action="open_application",
                last_verification={
                    "success": True,
                    "active": focused,
                    "window_id": win["window_id"],
                },
            )
            # Sync browser state if opening Chrome or Edge
            if canonical in {"google_chrome", "microsoft_edge"}:
                self.state.update(
                    browser_name=canonical,
                    browser=display,
                    browser_window_id=win["window_id"],
                )
            return {
                "success": True,
                "action": "open_application",
                "application": canonical,
                "display_name": display,
                "window_id": win["window_id"],
                "window_title": win["title"],
                "verification": "success",
                "message": f"{display} is open. What would you like me to do next?",
            }

        # 2. Launch application executable
        exe_path = resolved.executable
        if not exe_path:
            return {
                "success": False,
                "action": "open_application",
                "application": canonical,
                "error": f"No valid executable found for {display}.",
                "message": f"I couldn't open {display}. No executable found.",
            }

        try:
            logger.info("launching %s via %s", display, exe_path)
            if exe_path.lower().endswith(".lnk"):
                os.startfile(exe_path)
            else:
                cmd = [exe_path] + (args or [])
                subprocess.Popen(cmd, shell=False)
        except Exception as exc:  # noqa: BLE001
            try:
                os.startfile(exe_path)
            except Exception as fallback_exc:  # noqa: BLE001
                return {
                    "success": False,
                    "action": "open_application",
                    "application": canonical,
                    "error": f"Could not launch {display}: {exc} / {fallback_exc}",
                    "message": f"I couldn't open {display}. Launch failed: {exc}",
                }

        # 3. OBSERVE & VERIFY: Poll up to 4.5 seconds for window appearance
        verified_win: dict[str, Any] | None = None
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < 4.5:
            time.sleep(0.35)
            verified_win = self.window_controller.find_window(display, app_canonical=canonical)
            if not verified_win:
                verified_win = self.window_controller.find_window(
                    canonical.replace("_", " "), app_canonical=canonical
                )
            if not verified_win and canonical == "visual_studio_code":
                verified_win = self.window_controller.find_window("code", app_canonical=canonical)
            if not verified_win and canonical == "google_chrome":
                verified_win = self.window_controller.find_window("chrome", app_canonical=canonical)
            if not verified_win and canonical == "microsoft_edge":
                verified_win = self.window_controller.find_window("edge", app_canonical=canonical)
            if verified_win:
                break

        if verified_win:
            focused = self.window_controller.bring_to_front(verified_win["hwnd"])
            self.state.update(
                active_application=display,
                active_process=f"{canonical}.exe",
                active_window_id=verified_win["window_id"],
                active_window_title=verified_win["title"],
                last_action="open_application",
                last_verification={
                    "success": True,
                    "active": focused,
                    "window_id": verified_win["window_id"],
                },
            )
            if canonical in {"google_chrome", "microsoft_edge"}:
                self.state.update(
                    browser_name=canonical,
                    browser=display,
                    browser_window_id=verified_win["window_id"],
                )
            return {
                "success": True,
                "action": "open_application",
                "application": canonical,
                "display_name": display,
                "window_id": verified_win["window_id"],
                "window_title": verified_win["title"],
                "verification": "success",
                "message": f"{display} is open. What would you like me to do next?",
            }

        # NEVER claim false success without window verification
        return {
            "success": False,
            "action": "open_application",
            "application": canonical,
            "error": f"{display} window could not be verified in the foreground.",
            "message": f"I couldn't open {display}. The application window could not be verified.",
        }

    def close_application(self, app_name: str) -> dict[str, Any]:
        """Terminate an application safely and verify it closed."""
        canonical = app_name.strip().lower()
        if canonical not in CLOSEABLE_APPS:
            return {
                "success": False,
                "action": "close_application",
                "application": app_name,
                "error": f"Closing '{app_name}' is not permitted by the safety policy.",
            }

        terminated_count = 0
        search_terms = {canonical, f"{canonical}.exe"}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = (proc.info["name"] or "").lower()
                if pname in search_terms:
                    proc.terminate()
                    terminated_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Verify closure
        time.sleep(0.5)
        still_running, _ = self.is_application_running(canonical)
        if not still_running:
            if self.state.active_application and canonical in self.state.active_application.lower():
                self.state.active_application = None
                self.state.active_window_id = None
                self.state.active_window_title = None

            return {
                "success": True,
                "action": "close_application",
                "application": canonical.title(),
                "message": f"{canonical.title()} has been closed.",
            }

        return {
            "success": False,
            "action": "close_application",
            "application": canonical.title(),
            "error": f"Failed to fully terminate {canonical.title()}.",
        }

    def focus_application(self, app_name: str) -> dict[str, Any]:
        """Bring target application to foreground."""
        canonical = app_name.strip().lower()
        win = self.window_controller.find_window_by_title(canonical)
        if win:
            self.window_controller.focus_window(win["hwnd"])
            self.state.update(
                active_application=canonical.title(),
                active_window_id=win["window_id"],
                active_window_title=win["title"],
            )
            return {
                "success": True,
                "action": "focus_application",
                "application": canonical.title(),
                "message": f"Focused {canonical.title()}.",
            }
        return {
            "success": False,
            "action": "focus_application",
            "application": canonical.title(),
            "error": f"No active window found for {canonical.title()}.",
        }


default_app_controller = ApplicationController()

__all__ = ["ApplicationController", "default_app_controller"]
