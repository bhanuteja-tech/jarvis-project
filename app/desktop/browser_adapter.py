"""BrowserAdapter for JARVIS.

Provides the connection mechanism to observe and control browsers:
1. Connects to already-running Chrome/Edge instances via CDP (Chrome DevTools Protocol)
   using Playwright BrowserContext multi-page inspection and reuse when available.
2. Gracefully falls back to OS-level Windows UI Automation and WindowController
   when CDP remote debugging is not active or in unit-testing environments.
3. Extracts actual DOM observations (YouTube search results, channel titles, video links)
   so that current_list contains only ground-truth observed entities.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)

# Default remote debugging ports
DEFAULT_CDP_PORTS = (9222, 9223, 9224)


class BrowserAdapter:
    """Connects to and controls browser instances."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        cdp_port: int | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self._cdp_port = cdp_port
        self._playwright = None
        self._cdp_browser = None
        self._cdp_context = None
        self._is_cdp_connected = False

    @property
    def is_cdp_connected(self) -> bool:
        return self._is_cdp_connected

    async def connect_cdp(self, port: int | None = None) -> bool:
        """Attempt to connect to an already-running Chrome/Edge instance via CDP."""
        target_port = port or self._cdp_port or 9222
        endpoint = f"http://127.0.0.1:{target_port}"
        try:
            from playwright.async_api import async_playwright

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            self._cdp_browser = await self._playwright.chromium.connect_over_cdp(endpoint)
            contexts = self._cdp_browser.contexts
            self._cdp_context = contexts[0] if contexts else await self._cdp_browser.new_context()
            self._is_cdp_connected = True
            logger.info("Connected to already-running browser via CDP at %s", endpoint)
            return True
        except Exception as exc:
            logger.debug("CDP connection to %s not available: %s", endpoint, exc)
            self._is_cdp_connected = False
            return False

    async def get_cdp_pages(self) -> list[dict[str, Any]]:
        """Query open pages in the active Playwright BrowserContext."""
        if not self._is_cdp_connected or not self._cdp_context:
            return []
        try:
            pages = self._cdp_context.pages
            result = []
            for i, p in enumerate(pages):
                result.append({
                    "page_id": f"cdp_page_{i}",
                    "url": p.url,
                    "title": await p.title(),
                })
            return result
        except Exception as exc:
            logger.warning("Error fetching CDP pages: %s", exc)
            return []

    async def extract_observed_entities(self, page_type: str = "auto") -> list[dict[str, Any]]:
        """Extract ground-truth observed entities from active browser DOM/tree.

        Never invents fake items. Only returns elements actually present in the page.
        """
        if not self._is_cdp_connected or not self._cdp_context:
            return []

        try:
            pages = self._cdp_context.pages
            if not pages:
                return []
            active_p = pages[-1]
            url = active_p.url.lower()

            observed_items: list[dict[str, Any]] = []

            if "youtube.com" in url:
                # Query actual YouTube video title elements
                elements = await active_p.query_selector_all("ytd-video-renderer #video-title, ytd-rich-grid-media #video-title")
                for idx, el in enumerate(elements[:15]):
                    text = (await el.text_content() or "").strip()
                    href = await el.get_attribute("href")
                    if text and href:
                        full_url = href if href.startswith("http") else f"https://www.youtube.com{href}"
                        observed_items.append({
                            "type": "video",
                            "ordinal": idx + 1,
                            "title": text,
                            "url": full_url,
                            "source": "browser_dom_observation",
                            "observed_at": time.time(),
                        })

            return observed_items
        except Exception as exc:
            logger.warning("DOM entity extraction failed: %s", exc)
            return []

    def navigate_active_window(
        self,
        hwnd: int,
        url: str,
        *,
        force_new_tab: bool = False,
    ) -> bool:
        """Send navigation keystrokes to active browser window (Ctrl+L for reuse, Ctrl+T for new tab)."""
        self.window_controller.bring_to_front(hwnd)
        time.sleep(0.08)

        if force_new_tab:
            powershell_cmd = (
                "$wshell = New-Object -ComObject wscript.shell; "
                "$wshell.SendKeys('^t'); "
                "Start-Sleep -Milliseconds 150; "
                f"$wshell.SendKeys('{url}{{ENTER}}')"
            )
        else:
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
            return True
        except Exception as exc:
            logger.warning("PowerShell navigation failed: %s", exc)
            return False

    def send_key_combination(self, hwnd: int, keys: str) -> bool:
        """Send key combination like Alt+Left or Alt+Right to active window."""
        self.window_controller.bring_to_front(hwnd)
        time.sleep(0.05)
        cmd = f"$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('{keys}')"
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], timeout=3, check=False)
            return True
        except Exception as exc:
            logger.warning("Failed sending keys %s: %s", keys, exc)
            return False


default_browser_adapter = BrowserAdapter()

__all__ = ["BrowserAdapter", "default_browser_adapter"]
