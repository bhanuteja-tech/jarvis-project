"""Authoritative BrowserSession model for JARVIS.

Maintains browser context, window handle, open pages/tabs, active page,
and domain state following the Playwright BrowserContext multi-page model.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_domain(url: str | None) -> str | None:
    """Extract clean domain fragment from URL."""
    if not url:
        return None
    try:
        norm = url if url.startswith(("http://", "https://")) else f"https://{url}"
        netloc = urlparse(norm).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return None


@dataclass
class BrowserPage:
    """Represents a single tab/page in the browser context."""

    page_id: str
    url: str
    title: str
    domain: str
    timestamp: float = field(default_factory=time.time)
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "timestamp": self.timestamp,
            "is_active": self.is_active,
        }


@dataclass
class BrowserSession:
    """Authoritative browser session maintaining:

    browser, window, context, pages/tabs, active_page, url, title, domain.
    Enforces strict page reuse to prevent unnecessary tab creation.
    """

    browser: str = "google_chrome"
    explicit_browser: bool = False
    window_id: str | None = None
    hwnd: int | None = None
    context_id: str = "default_context"
    pages: list[BrowserPage] = field(default_factory=list)
    active_page_id: str | None = None
    _page_counter: int = 0

    @property
    def active_page(self) -> BrowserPage | None:
        if not self.pages:
            return None
        if self.active_page_id:
            for p in self.pages:
                if p.page_id == self.active_page_id:
                    return p
        return self.pages[-1]

    @property
    def url(self) -> str | None:
        p = self.active_page
        return p.url if p else None

    @property
    def title(self) -> str | None:
        p = self.active_page
        return p.title if p else None

    @property
    def domain(self) -> str | None:
        p = self.active_page
        return p.domain if p else None

    def find_compatible_page(self, target_url_or_domain: str) -> BrowserPage | None:
        """Find an existing open page that matches the target service/domain for reuse."""
        target_norm = target_url_or_domain.lower().strip()
        target_domain = extract_domain(target_norm) or target_norm

        # 1. First check if active page is already compatible
        if self.active_page:
            ap_domain = self.active_page.domain
            if target_domain and ap_domain and (target_domain in ap_domain or ap_domain in target_domain):
                return self.active_page
            if "youtube" in target_domain and "youtube.com" in (self.active_page.url or "").lower():
                return self.active_page

        # 2. Check all open pages
        for p in self.pages:
            if target_domain and p.domain and (target_domain in p.domain or p.domain in target_domain):
                return p
            if "youtube" in target_domain and "youtube.com" in (p.url or "").lower():
                return p

        return None

    def record_or_reuse_page(
        self,
        url: str,
        title: str | None = None,
        *,
        force_new_tab: bool = False,
    ) -> tuple[BrowserPage, str]:
        """Resolve whether to reuse an existing page or register a new one.

        Returns: (page, resolution_action)
        """
        dom = extract_domain(url) or ""

        if not force_new_tab:
            compatible = self.find_compatible_page(url)
            if compatible:
                compatible.url = url
                if title:
                    compatible.title = title
                compatible.domain = dom
                compatible.timestamp = time.time()
                self.set_active_page(compatible.page_id)
                action = "reused_active" if compatible.page_id == self.active_page_id else "reused_existing"
                logger.info("BrowserSession: %s page %s (%s)", action, compatible.page_id, url)
                return compatible, action

        # Create new page
        self._page_counter += 1
        page_id = f"page_{self._page_counter:04d}"
        new_page = BrowserPage(
            page_id=page_id,
            url=url,
            title=title or url,
            domain=dom,
            timestamp=time.time(),
            is_active=True,
        )
        self.pages.append(new_page)
        self.set_active_page(page_id)
        logger.info("BrowserSession: created new page %s (%s)", page_id, url)
        return new_page, "created_new"

    def set_active_page(self, page_id: str) -> None:
        self.active_page_id = page_id
        for p in self.pages:
            p.is_active = (p.page_id == page_id)

    def close_page(self, page_id: str | None = None) -> bool:
        target_id = page_id or self.active_page_id
        if not target_id:
            return False
        self.pages = [p for p in self.pages if p.page_id != target_id]
        if self.pages:
            self.active_page_id = self.pages[-1].page_id
            self.pages[-1].is_active = True
        else:
            self.active_page_id = None
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "browser": self.browser,
            "explicit_browser": self.explicit_browser,
            "window_id": self.window_id,
            "context_id": self.context_id,
            "active_page_id": self.active_page_id,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "pages": [p.to_dict() for p in self.pages],
            "pages_count": len(self.pages),
        }
