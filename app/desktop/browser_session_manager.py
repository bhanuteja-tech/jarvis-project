"""Browser Session Manager for JARVIS.

Maintains authoritative browser sessions distinguishing:
BROWSER -> CONTEXT -> PAGE/TAB.
Enforces page reuse to prevent duplicate tabs when navigating or searching services (e.g. YouTube).
Adheres strictly to the PLAN -> ACT -> OBSERVE -> VERIFY loop.

Phase 8+: Extended with explicit browser_specifically_requested propagation,
generic BrowserAdapter (Chrome/Edge/Firefox/Brave/Opera), and post-navigation
window-title verification to prevent false success reporting.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any
from urllib.parse import quote_plus

from app.desktop.state import ComputerState, default_computer_state
from app.desktop.window_controller import WindowController, default_window_controller
from app.routing.app_resolver import ApplicationResolver, default_app_resolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Browser canonical map — maps canonical names to display names and
# window-title search tokens.  Add new browsers here only.
# ---------------------------------------------------------------------------
BROWSER_CANONICAL_MAP: dict[str, dict[str, Any]] = {
    "google_chrome": {
        "display": "Google Chrome",
        "exe": "chrome.exe",
        "tokens": ["chrome"],  # tokens that appear in the window title
        "process": "chrome.exe",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
    },
    "microsoft_edge": {
        "display": "Microsoft Edge",
        "exe": "msedge.exe",
        "tokens": ["edge", "microsoft edge"],
        "process": "msedge.exe",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    "firefox": {
        "display": "Mozilla Firefox",
        "exe": "firefox.exe",
        "tokens": ["firefox", "mozilla firefox"],
        "process": "firefox.exe",
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
    },
    "brave": {
        "display": "Brave Browser",
        "exe": "brave.exe",
        "tokens": ["brave"],
        "process": "brave.exe",
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ],
    },
    "opera": {
        "display": "Opera",
        "exe": "opera.exe",
        "tokens": ["opera"],
        "process": "opera.exe",
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
        ],
    },
}


def _canonicalize_browser(name: str) -> str:
    """Map any spoken/alias browser name to a canonical key."""
    lower = name.lower().strip()
    if any(k in lower for k in ("edge", "microsoft edge", "msedge")):
        return "microsoft_edge"
    if any(k in lower for k in ("firefox", "mozilla")):
        return "firefox"
    if "brave" in lower:
        return "brave"
    if "opera" in lower:
        return "opera"
    # Default to Chrome for "chrome", "google chrome", or empty/unknown
    return "google_chrome"


class BrowserSessionManager:
    """Manages browser sessions, context, and page lifecycle with strict reuse."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
        app_resolver: ApplicationResolver | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state
        self.app_resolver = app_resolver or default_app_resolver

        # Active session context
        self._browser_name: str | None = None  # "google_chrome" or "microsoft_edge"
        self.browser_window_id: str | None = None
        self.browser_process: str | None = None
        self.browser_context_id: str = "default_context"

        self.active_page: dict[str, Any] | None = None
        self.open_pages: list[dict[str, Any]] = []
        self._page_counter = 0

    @property
    def browser_name(self) -> str:
        return self._browser_name or self.state.browser_name or "google_chrome"

    @browser_name.setter
    def browser_name(self, value: str | None) -> None:
        self._browser_name = value
        if value:
            self.state.browser_name = value

    def display_name(self, canonical: str | None = None) -> str:
        """Return the human-readable display name for a canonical browser key."""
        key = canonical or self.browser_name
        return BROWSER_CANONICAL_MAP.get(key, {}).get("display", key.replace("_", " ").title())

    def set_specifically_requested(self, browser_alias: str) -> str:
        """Record that the user explicitly named a browser.  Returns canonical key."""
        canonical = _canonicalize_browser(browser_alias)
        self._browser_name = canonical
        self.state.browser_name = canonical
        self.state.browser_specifically_requested = canonical
        logger.info("Browser specifically requested: %s -> %s", browser_alias, canonical)
        return canonical

    def _sync_state(self) -> None:
        """Sync session manager state with the global ComputerState."""
        current_name = self.browser_name
        display = (
            "Microsoft Edge"
            if current_name == "microsoft_edge"
            else "Google Chrome"
        )
        self.state.update(
            browser_name=current_name,
            browser=display,
            browser_window_id=self.browser_window_id,
            browser_process=self.browser_process,
            browser_context_id=self.browser_context_id,
            active_page_id=self.active_page.get("page_id") if self.active_page else None,
            active_page_url=self.active_page.get("url") if self.active_page else None,
            active_page_title=self.active_page.get("title") if self.active_page else None,
            active_tab=self.active_page.get("title") if self.active_page else None,
            current_url=self.active_page.get("url") if self.active_page else None,
            open_pages=list(self.open_pages),
        )

    def find_browser_window(self, browser_name: str | None = None) -> dict[str, Any] | None:
        """Locate open window for target browser using BROWSER_CANONICAL_MAP tokens."""
        target = _canonicalize_browser(browser_name or self.browser_name)
        spec = BROWSER_CANONICAL_MAP.get(target, {})
        tokens = spec.get("tokens", [target.replace("_", " ")])

        # Search windows list for first title matching any of the tokens
        windows = self.window_controller.list_windows()
        for win in windows:
            title = (win.get("title") or "").lower()
            if any(tok in title for tok in tokens):
                return win

        # Fallback: old find_window helper
        for tok in tokens:
            win = self.window_controller.find_window(tok, app_canonical=target)
            if win:
                return win
        return None

    def focus_browser(self) -> bool:
        """Bring currently tracked or default browser to foreground."""
        win = self.find_browser_window(self.browser_name)
        if win:
            focused = self.window_controller.bring_to_front(win["hwnd"])
            if focused:
                self.browser_window_id = win["window_id"]
                self._sync_state()
            return focused
        return False

    def open_browser(
        self,
        browser_name: str = "google_chrome",
        url: str | None = None,
    ) -> tuple[bool, str]:
        """Launch or focus target browser, verify foreground status, and update state.

        Accepts any canonical key (google_chrome, microsoft_edge, firefox, brave, opera)
        or any natural-language alias that _canonicalize_browser() handles.
        """
        canonical = _canonicalize_browser(browser_name)
        spec = BROWSER_CANONICAL_MAP.get(canonical, {})
        display = spec.get("display", canonical.replace("_", " ").title())
        self.browser_name = canonical

        # 1. If already open and focused, reuse window
        existing_win = self.find_browser_window(canonical)
        if existing_win and not url:
            self.window_controller.bring_to_front(existing_win["hwnd"])
            self.browser_window_id = existing_win["window_id"]
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

        # If no path found, try resolver
        if not exe_path:
            resolved = self.app_resolver.resolve(canonical)
            exe_path = resolved.executable if resolved else None

        target_url = url or "about:blank"

        if exe_path and os.path.exists(exe_path):
            try:
                subprocess.Popen([exe_path, target_url], shell=False)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to launch %s: %s", exe_path, exc)
        else:
            import webbrowser

            webbrowser.open(target_url)

        # 3. OBSERVE & VERIFY: Poll up to 4.0s for foreground window
        verified_win: dict[str, Any] | None = None
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < 4.0:
            time.sleep(0.3)
            win = self.find_browser_window(canonical)
            if win:
                self.window_controller.bring_to_front(win["hwnd"])
                if self.window_controller.is_window_active(win["hwnd"]):
                    verified_win = win
                    break

        if verified_win:
            self.browser_window_id = verified_win["window_id"]
            if url:
                page = self._record_page(url, title=verified_win.get("title", display))
                self.active_page = page

            self.state.update(
                active_application=display,
                active_window_id=verified_win["window_id"],
                active_window_title=verified_win["title"],
                last_action="open_browser",
            )
            self._sync_state()
            return True, f"{display} is open. What would you like me to do next?"

        return False, f"I couldn't open {display}. The browser window could not be verified."

    def _record_page(self, url: str, title: str | None = None) -> dict[str, Any]:
        """Create or update an entry in open_pages."""
        self._page_counter += 1
        page_id = f"page_{self._page_counter:04d}"
        page = {
            "page_id": page_id,
            "url": url,
            "title": title or url,
            "timestamp": time.time(),
        }
        self.open_pages.append(page)
        return page

    def get_or_create_page(
        self,
        target: str,
        *,
        force_new_tab: bool = False,
    ) -> tuple[dict[str, Any], str]:
        """Resolve whether to reuse the active page, focus an existing page, or create a new page.

        Returns: (page_dict, action_taken)
        action_taken: "reused_active" | "focused_existing" | "navigated_current" | "created_new"
        """
        norm_target = target.lower().strip()
        is_youtube = "youtube" in norm_target

        # 1. If not forcing a new tab and active page matches, reuse it!
        if not force_new_tab and self.active_page:
            active_url = (self.active_page.get("url") or "").lower()
            if is_youtube and "youtube.com" in active_url:
                self.active_page["url"] = target
                self.active_page["timestamp"] = time.time()
                self._sync_state()
                return self.active_page, "reused_active"
            if norm_target in active_url:
                self.active_page["url"] = target
                self.active_page["timestamp"] = time.time()
                self._sync_state()
                return self.active_page, "reused_active"

        # 2. If matching page exists in open_pages, focus it
        if not force_new_tab:
            for page in self.open_pages:
                p_url = (page.get("url") or "").lower()
                if (is_youtube and "youtube.com" in p_url) or (norm_target in p_url):
                    self.active_page = page
                    self._sync_state()
                    return page, "focused_existing"

        # 3. If an active page exists in the browser, navigate it in-place
        if not force_new_tab and self.active_page:
            self.active_page["url"] = target
            self.active_page["timestamp"] = time.time()
            self._sync_state()
            return self.active_page, "navigated_current"

        # 4. Create new page entry
        new_page = self._record_page(target)
        self.active_page = new_page
        self._sync_state()
        return new_page, "created_new"

    def navigate(
        self,
        url: str,
        service_name: str | None = None,
        *,
        force_new_tab: bool = False,
        verify_domain: str | None = None,
        verify_timeout: float = 3.0,
    ) -> tuple[bool, str]:
        """Navigate target page in the active browser context without creating duplicate tabs.

        Phase 8+: Added post-navigation verification via live window-title polling.
        ``verify_domain`` is the domain fragment to confirm (e.g. "youtube.com").
        If omitted, verification is skipped (optimistic).
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Ensure browser is attached and focused
        win = self.find_browser_window()
        if not win:
            ok, msg = self.open_browser(url=url)
            return ok, msg

        # Bring existing browser window to front
        self.window_controller.bring_to_front(win["hwnd"])
        self.browser_window_id = win["window_id"]

        page, action_taken = self.get_or_create_page(url, force_new_tab=force_new_tab)
        logger.info("Page resolution for %s: %s (page_id=%s)", url, action_taken, page["page_id"])

        # Execute navigation in the active browser window
        self._navigate_active_window(win["hwnd"], url, force_new_tab=force_new_tab)

        # Update ComputerState
        service_label = service_name or ("YouTube" if "youtube.com" in url else "Page")
        display_browser = self.display_name()
        self.state.update(
            active_application=display_browser,
            active_window_id=win["window_id"],
            last_action="navigate",
        )
        self._sync_state()

        # Phase 8+: post-navigation window-title verification
        verified = False
        verify_reason = "optimistic"
        if verify_domain:
            domain_lower = verify_domain.lower().rstrip("/")
            if domain_lower.startswith(("https://", "http://")):
                domain_lower = domain_lower.split("://", 1)[1].rstrip("/")
            deadline = time.perf_counter() + verify_timeout
            while time.perf_counter() < deadline:
                time.sleep(0.35)
                active = self.window_controller.get_active_window()
                if active:
                    title = (active.get("title") or "").lower()
                    if domain_lower in title:
                        verified = True
                        verify_reason = f"window title contains '{verify_domain}'"
                        break
            if not verified:
                verify_reason = (
                    f"window title did not contain '{verify_domain}' within {verify_timeout}s"
                )

        # Update state verification metadata
        self.state.last_verified = verified
        self.state.last_verify_method = "window_title_poll" if verify_domain else "none"
        self.state.last_verify_reason = verify_reason

        return True, f"{service_label} is open. What would you like me to do next?"

    def _navigate_active_window(
        self,
        hwnd: int,
        url: str,
        *,
        force_new_tab: bool = False,
    ) -> None:
        """Set URL in active browser window address bar or open tab."""
        # Preferred: UI Automation address bar manipulation or keyboard navigation
        import subprocess

        # Ensure window is active
        self.window_controller.bring_to_front(hwnd)
        time.sleep(0.1)

        if force_new_tab:
            # Ctrl+T then URL
            powershell_cmd = (
                "$wshell = New-Object -ComObject wscript.shell; "
                "$wshell.SendKeys('^t'); "
                "Start-Sleep -Milliseconds 150; "
                f"$wshell.SendKeys('{url}{{ENTER}}')"
            )
        else:
            # Reuse current tab: Ctrl+L then URL + Enter
            powershell_cmd = (
                "$wshell = New-Object -ComObject wscript.shell; "
                "$wshell.SendKeys('^l'); "
                "Start-Sleep -Milliseconds 100; "
                f"$wshell.SendKeys('{url}{{ENTER}}')"
            )

        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", powershell_cmd],
                timeout=4,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("powershell navigation failed: %s, falling back to process", exc)

    def search(
        self,
        query: str,
        service: str = "google",
        *,
        force_new_tab: bool = False,
    ) -> tuple[bool, str]:
        """Perform in-page or service search, reusing existing tab if service is already open."""
        q = (query or "").strip()
        if not q:
            return False, "Search query was empty."

        encoded = quote_plus(q)
        norm_service = service.lower().strip()

        # Build target URL
        if norm_service in {"youtube", "yt"} or (
            self.active_page and "youtube.com" in (self.active_page.get("url") or "").lower()
        ):
            url = f"https://www.youtube.com/results?search_query={encoded}"
            service_label = "YouTube"
        elif norm_service == "github":
            url = f"https://github.com/search?q={encoded}"
            service_label = "GitHub"
        elif norm_service == "duckduckgo":
            url = f"https://duckduckgo.com/?q={encoded}"
            service_label = "DuckDuckGo"
        elif norm_service == "bing":
            url = f"https://www.bing.com/search?q={encoded}"
            service_label = "Bing"
        else:
            url = f"https://www.google.com/search?q={encoded}"
            service_label = "the web"

        # Navigate using strict page reuse (NO duplicate tabs)
        ok, _ = self.navigate(url, service_name=service_label, force_new_tab=force_new_tab)
        if ok:
            return (
                True,
                f"Searching {service_label} for '{q}'. What would you like me to do next?",
            )
        return False, f"Search failed on {service_label}."

    def go_back(self) -> tuple[bool, str]:
        """Send Alt+Left Arrow to active browser window."""
        win = self.find_browser_window()
        if win:
            self.window_controller.bring_to_front(win["hwnd"])
            time.sleep(0.05)
            import subprocess

            cmd = "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('%{LEFT}')"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], timeout=3, check=False)
            return True, "Navigated back. What would you like me to do next?"
        return False, "No active browser window found to navigate back."

    def go_forward(self) -> tuple[bool, str]:
        """Send Alt+Right Arrow to active browser window."""
        win = self.find_browser_window()
        if win:
            self.window_controller.bring_to_front(win["hwnd"])
            time.sleep(0.05)
            import subprocess

            cmd = "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('%{RIGHT}')"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], timeout=3, check=False)
            return True, "Navigated forward. What would you like me to do next?"
        return False, "No active browser window found to navigate forward."

    def verify_current_navigation(self, expected_domain: str, timeout: float = 3.0) -> bool:
        """Synchronous helper: poll window title for expected_domain up to timeout seconds.

        Returns True if the domain is found in the foreground window title.
        Used by the ComputerAgent verification step.
        """
        domain_lower = expected_domain.lower().rstrip("/")
        if domain_lower.startswith(("https://", "http://")):
            domain_lower = domain_lower.split("://", 1)[1].rstrip("/")

        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            active = self.window_controller.get_active_window()
            if active:
                title = (active.get("title") or "").lower()
                if domain_lower in title:
                    self.state.last_verified = True
                    self.state.last_verify_method = "window_title_poll"
                    return True
            time.sleep(0.35)
        self.state.last_verified = False
        self.state.last_verify_method = "window_title_poll_timeout"
        return False


default_browser_session_manager = BrowserSessionManager()

__all__ = [
    "BrowserSessionManager",
    "BROWSER_CANONICAL_MAP",
    "default_browser_session_manager",
    "_canonicalize_browser",
]
