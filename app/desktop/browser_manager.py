"""BrowserManager for JARVIS.

Central controller for browser lifecycle, target resolution, and tab reuse:
1. Maintains authoritative BrowserSession state (browser, window, context, pages, active_page, url, title, domain).
2. Enforces explicit vs implicit browser resolution ("Open YouTube in Edge" -> Edge explicit, "Open YouTube" -> default policy).
3. Reuses existing compatible pages to prevent duplicate tabs when navigating or searching services (e.g. YouTube).
4. Verifies foreground window and URL/title postconditions.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any
from urllib.parse import quote_plus

from app.desktop.browser_adapter import BrowserAdapter, default_browser_adapter
from app.desktop.browser_session import BrowserSession, extract_domain
from app.desktop.browser_session_manager import BROWSER_CANONICAL_MAP, _canonicalize_browser
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.window_controller import WindowController, default_window_controller
from app.routing.app_resolver import ApplicationResolver, default_app_resolver

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages browser sessions, target resolution, and strict page reuse."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
        adapter: BrowserAdapter | None = None,
        app_resolver: ApplicationResolver | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state
        self.adapter = adapter or default_browser_adapter
        self.app_resolver = app_resolver or default_app_resolver

        # Active BrowserSession
        self.session = BrowserSession()

    @property
    def browser_name(self) -> str:
        return self.session.browser or self.state.browser_name or "google_chrome"

    def display_name(self, canonical: str | None = None) -> str:
        key = canonical or self.browser_name
        return BROWSER_CANONICAL_MAP.get(key, {}).get("display", key.replace("_", " ").title())

    def resolve_browser_target(
        self,
        explicit_browser: str | None = None,
    ) -> tuple[str, bool]:
        """Resolve target browser according to explicit vs implicit policy.

        Returns (canonical_browser, is_explicit).
        Never silently switches if a browser was specifically requested.
        """
        if explicit_browser:
            canonical = _canonicalize_browser(explicit_browser)
            self.session.browser = canonical
            self.session.explicit_browser = True
            self.state.browser_name = canonical
            self.state.browser_specifically_requested = canonical
            return canonical, True

        # Check if browser was previously specifically requested
        if self.state.browser_specifically_requested:
            return self.state.browser_specifically_requested, True

        # Use current active browser or default policy
        current = self.session.browser or self.state.browser_name or "google_chrome"
        return current, False

    def find_browser_window(self, browser_name: str | None = None) -> dict[str, Any] | None:
        """Find open window handle for browser."""
        target = _canonicalize_browser(browser_name or self.browser_name)
        spec = BROWSER_CANONICAL_MAP.get(target, {})
        tokens = spec.get("tokens", [target.replace("_", " ")])

        windows = self.window_controller.list_windows()
        for win in windows:
            title = (win.get("title") or "").lower()
            if any(tok in title for tok in tokens):
                return win

        for tok in tokens:
            win = self.window_controller.find_window(tok, app_canonical=target)
            if win:
                return win
        return None

    def focus_browser(self, browser_name: str | None = None) -> bool:
        """Bring tracked browser window to foreground."""
        target = browser_name or self.browser_name
        win = self.find_browser_window(target)
        if win:
            focused = self.window_controller.bring_to_front(win["hwnd"])
            if focused:
                self.session.window_id = win["window_id"]
                self.session.hwnd = win["hwnd"]
                self._sync_state()
            return focused
        return False

    def open_browser(
        self,
        browser_name: str | None = None,
        url: str | None = None,
        *,
        explicit: bool = False,
    ) -> tuple[bool, str]:
        """Launch or focus target browser.

        Enforces browser target resolution and records explicit choice.
        """
        canonical, is_explicit = self.resolve_browser_target(browser_name if explicit else None)
        if browser_name and not is_explicit:
            canonical = _canonicalize_browser(browser_name)
        self.session.browser = canonical
        self.session.explicit_browser = is_explicit

        display = self.display_name(canonical)

        # 1. If already open and focused, reuse window
        existing_win = self.find_browser_window(canonical)
        if existing_win and not url:
            self.window_controller.bring_to_front(existing_win["hwnd"])
            self.session.window_id = existing_win["window_id"]
            self.session.hwnd = existing_win["hwnd"]
            self.state.update(
                active_application=display,
                active_window_id=existing_win["window_id"],
                active_window_title=existing_win["title"],
                last_action="open_browser",
            )
            self._sync_state()
            return True, f"{display} is open. What would you like me to do next?"

        # 2. Launch browser process
        spec = BROWSER_CANONICAL_MAP.get(canonical, {})
        paths = spec.get("paths", [])
        exe_path: str | None = None
        for p in paths:
            if p and os.path.exists(p):
                exe_path = p
                break

        if not exe_path:
            resolved = self.app_resolver.resolve(canonical)
            exe_path = resolved.executable if resolved else None

        target_url = url or "about:blank"

        if exe_path and os.path.exists(exe_path):
            try:
                subprocess.Popen([exe_path, target_url], shell=False)
            except Exception as exc:
                logger.error("Failed to launch %s: %s", exe_path, exc)
        else:
            import webbrowser
            webbrowser.open(target_url)

        # 3. Observe & Verify: Poll for foreground window
        start_time = time.perf_counter()
        verified_win = None
        while time.perf_counter() - start_time < 4.0:
            time.sleep(0.25)
            win = self.find_browser_window(canonical)
            if win:
                self.window_controller.bring_to_front(win["hwnd"])
                if self.window_controller.is_window_active(win["hwnd"]):
                    verified_win = win
                    break

        if verified_win:
            self.session.window_id = verified_win["window_id"]
            self.session.hwnd = verified_win["hwnd"]
            if url:
                page, _ = self.session.record_or_reuse_page(url, title=verified_win.get("title", display))
            self.state.update(
                active_application=display,
                active_window_id=verified_win["window_id"],
                active_window_title=verified_win["title"],
                last_action="open_browser",
            )
            self._sync_state()
            return True, f"{display} is open. What would you like me to do next?"

        return False, f"I couldn't verify that {display} opened."

    def navigate(
        self,
        url: str,
        service_name: str | None = None,
        *,
        explicit_browser: str | None = None,
        force_new_tab: bool = False,
        verify_domain: str | None = None,
        verify_timeout: float = 3.0,
    ) -> tuple[bool, str]:
        """Navigate page with strict reuse of existing compatible tab."""
        canonical, _ = self.resolve_browser_target(explicit_browser)

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        win = self.find_browser_window(canonical)
        if not win:
            ok, msg = self.open_browser(browser_name=canonical, url=url, explicit=bool(explicit_browser))
            return ok, msg

        self.window_controller.bring_to_front(win["hwnd"])
        self.session.window_id = win["window_id"]
        self.session.hwnd = win["hwnd"]

        # Page reuse check
        page, action_taken = self.session.record_or_reuse_page(url, force_new_tab=force_new_tab)
        logger.info("BrowserManager page resolution: %s for %s", action_taken, url)

        # Send navigation keystrokes
        self.adapter.navigate_active_window(win["hwnd"], url, force_new_tab=force_new_tab)

        display = self.display_name(canonical)
        service_label = service_name or ("YouTube" if "youtube.com" in url else "Page")

        self.state.update(
            active_application=display,
            active_window_id=win["window_id"],
            last_action="navigate",
        )
        self._sync_state()

        # Window title verification if requested
        verified = False
        verify_reason = "optimistic"
        if verify_domain:
            domain_clean = verify_domain.lower().rstrip("/")
            if domain_clean.startswith(("http://", "https://")):
                domain_clean = extract_domain(domain_clean) or domain_clean

            deadline = time.perf_counter() + verify_timeout
            while time.perf_counter() < deadline:
                time.sleep(0.3)
                active = self.window_controller.get_active_window()
                if active:
                    title = (active.get("title") or "").lower()
                    if domain_clean in title:
                        verified = True
                        verify_reason = f"window title contains '{verify_domain}'"
                        break
            if not verified:
                verify_reason = f"window title did not contain '{verify_domain}' within {verify_timeout}s"

        self.state.last_verified = verified
        self.state.last_verify_method = "window_title_poll" if verify_domain else "none"
        self.state.last_verify_reason = verify_reason

        return True, f"{service_label} is open. What would you like me to do next?"

    def search(
        self,
        query: str,
        service: str = "google",
        *,
        explicit_browser: str | None = None,
        force_new_tab: bool = False,
    ) -> tuple[bool, str]:
        """Perform search with tab reuse on the target service."""
        q = (query or "").strip()
        if not q:
            return False, "Search query was empty."

        encoded = quote_plus(q)
        norm_svc = service.lower().strip()

        # Build target search URL
        if norm_svc in {"youtube", "yt"} or (
            self.session.url and "youtube.com" in self.session.url.lower()
        ):
            url = f"https://www.youtube.com/results?search_query={encoded}"
            service_label = "YouTube"
        elif norm_svc == "github":
            url = f"https://github.com/search?q={encoded}"
            service_label = "GitHub"
        elif norm_svc == "duckduckgo":
            url = f"https://duckduckgo.com/?q={encoded}"
            service_label = "DuckDuckGo"
        elif norm_svc == "bing":
            url = f"https://www.bing.com/search?q={encoded}"
            service_label = "Bing"
        else:
            url = f"https://www.google.com/search?q={encoded}"
            service_label = "the web"

        ok, _ = self.navigate(
            url,
            service_name=service_label,
            explicit_browser=explicit_browser,
            force_new_tab=force_new_tab,
            verify_domain=service_label.lower(),
        )
        if ok:
            return True, f"Searching {service_label} for '{q}'. What would you like me to do next?"
        return False, f"Search failed on {service_label}."

    def go_back(self) -> tuple[bool, str]:
        win = self.find_browser_window()
        if win:
            ok = self.adapter.send_key_combination(win["hwnd"], "%{LEFT}")
            if ok:
                return True, "Navigated back. What would you like me to do next?"
        return False, "No active browser window found to navigate back."

    def go_forward(self) -> tuple[bool, str]:
        win = self.find_browser_window()
        if win:
            ok = self.adapter.send_key_combination(win["hwnd"], "%{RIGHT}")
            if ok:
                return True, "Navigated forward. What would you like me to do next?"
        return False, "No active browser window found to navigate forward."

    def _sync_state(self) -> None:
        """Synchronize BrowserSession state into authoritative ComputerState."""
        display = self.display_name()
        self.state.update(
            browser_name=self.session.browser,
            browser=display,
            browser_window_id=self.session.window_id,
            browser_context_id=self.session.context_id,
            active_page_id=self.session.active_page.page_id if self.session.active_page else None,
            active_page_url=self.session.url,
            active_page_title=self.session.title,
            current_url=self.session.url,
            open_pages=[p.to_dict() for p in self.session.pages],
        )


default_browser_manager = BrowserManager()

__all__ = ["BrowserManager", "default_browser_manager"]
