"""Optional Layer-4 browser rendering via Playwright.

Deliberately OPTIONAL:
- the ``playwright`` package is an extra (``pip install .[browser]``) and its
  browser binaries are installed separately (``playwright install chromium``);
- this module lazy-imports playwright so the rest of the extractor works
  without it;
- rendering is triggered ONLY when static layers yield insufficient evidence
  AND SPA indicators are present AND ``career_browser_enabled`` is set.

Safety constraints (approved):
- headless Chromium only; ONE navigation per render; no interaction
  (no clicks/typing/scroll injection), no downloads, no credentials;
- third-party heavy resources (images/media/fonts) are aborted at the route
  layer for speed and safety — also required during live smoke;
- global concurrency limited by a semaphore; context is always closed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from dataclasses import dataclass

from app.config.settings import Settings
from app.sources.career.errors import CareerPageError

logger = logging.getLogger(__name__)

_NAVIGATION_TIMEOUT_MS = 15_000
_SETTLE_MS = 300
_MAX_CONCURRENT_RENDERS = 2

_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})


@dataclass(frozen=True)
class RenderedPage:
    html: str
    final_url: str


class BrowserUnavailableError(CareerPageError):
    """Playwright extra/binary not installed."""


class BrowserRenderer:
    _semaphore: asyncio.Semaphore | None = None

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("playwright") is not None

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_RENDERS)
        return cls._semaphore

    async def render(self, url: str) -> RenderedPage:
        if not self.available():
            raise BrowserUnavailableError(
                "playwright is not installed",
                reason="browser_unavailable",
                url=url,
            )

        from playwright.async_api import async_playwright  # lazy import

        async with BrowserRenderer._get_semaphore():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        accept_downloads=False,
                        viewport={"width": 1280, "height": 800},
                    )
                    try:
                        await context.route("**/*", self._route_handler)
                        page = await context.new_page()
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=_NAVIGATION_TIMEOUT_MS,
                        )
                        final_url = page.url or url
                        await page.wait_for_timeout(_SETTLE_MS)
                        html = await page.content()
                    finally:
                        await context.close()
                finally:
                    await browser.close()

        logger.info(
            "browser render complete",
            extra={
                "source": "career_page",
                "operation": "render",
                "url": url,
                "html_bytes": len(html),
            },
        )
        return RenderedPage(html=html, final_url=final_url)

    @staticmethod
    async def _route_handler(route) -> None:  # type: ignore[no-untyped-def]
        request = route.request
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        await route.continue_()


__all__ = ["BrowserRenderer", "BrowserUnavailableError", "RenderedPage"]
