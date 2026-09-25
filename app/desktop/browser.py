"""Browser Controller and session state manager for the JARVIS Agent Harness.

Maintains active browser context, reuses existing browser windows/pages,
and delegates to BrowserSessionManager for strict duplicate-tab prevention.
"""

from __future__ import annotations

import logging

from app.desktop.browser_session_manager import (
    BrowserSessionManager,
    default_browser_session_manager,
)
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)


class BrowserController:
    """Controls browser windows and tracks active navigation session."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
        session_manager: BrowserSessionManager | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state
        self.session_manager = session_manager or default_browser_session_manager
        self._history: list[str] = []

    @property
    def last_url(self) -> str | None:
        return self.state.current_url

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def focus_browser(self) -> bool:
        """Bring tracked browser window to foreground."""
        return self.session_manager.focus_browser()

    def open_browser(
        self,
        url: str | None = None,
        browser_name: str | None = None,
    ) -> tuple[bool, str]:
        """Launch or focus browser (respecting active browser choice)."""
        target_browser = browser_name or self.state.browser_name or "google_chrome"
        ok, msg = self.session_manager.open_browser(browser_name=target_browser, url=url)
        if ok and url:
            self._history.append(url)
        return ok, msg

    def navigate(
        self,
        url: str,
        service_name: str | None = None,
        *,
        force_new_tab: bool = False,
    ) -> tuple[bool, str]:
        """Navigate active browser context to a specified URL with page reuse."""
        ok, msg = self.session_manager.navigate(
            url, service_name=service_name, force_new_tab=force_new_tab
        )
        if ok:
            self._history.append(url)
        return ok, msg

    def search(
        self,
        query: str,
        engine: str = "google",
        *,
        force_new_tab: bool = False,
    ) -> tuple[bool, str]:
        """Perform a web or in-service search using current context and tab reuse."""
        ok, msg = self.session_manager.search(query, service=engine, force_new_tab=force_new_tab)
        if ok and self.state.current_url:
            self._history.append(self.state.current_url)
        return ok, msg

    def go_back(self) -> tuple[bool, str]:
        """Navigate back in browser history if available."""
        return self.session_manager.go_back()

    def go_forward(self) -> tuple[bool, str]:
        """Navigate forward in browser history if available."""
        return self.session_manager.go_forward()


# Global controller instance
default_browser = BrowserController()

__all__ = ["BrowserController", "default_browser"]
