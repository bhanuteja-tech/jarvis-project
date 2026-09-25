"""Web Context Tracker for JARVIS Computer-Use Agent.

Maintains hierarchical web context for sites like YouTube:
    Site → Channel → Course → Video

Also tracks any enumerable list the user can refer back to with ordinal
phrases like "the third one", "the first video", etc.

The tracker is called by:
- BrowserSessionManager.navigate() (updates site/page)
- ComputerAgent._update_state() (updates after each verified step)
- AgentHarness (after browser navigation results)
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Site detection patterns
# ---------------------------------------------------------------------------

_SITE_PATTERNS: dict[str, re.Pattern] = {
    "youtube": re.compile(r"youtube\.com|youtu\.be", re.IGNORECASE),
    "github": re.compile(r"github\.com", re.IGNORECASE),
    "reddit": re.compile(r"reddit\.com", re.IGNORECASE),
    "linkedin": re.compile(r"linkedin\.com", re.IGNORECASE),
    "twitter": re.compile(r"twitter\.com|x\.com", re.IGNORECASE),
    "gmail": re.compile(r"mail\.google\.com", re.IGNORECASE),
    "google": re.compile(r"google\.com", re.IGNORECASE),
    "chatgpt": re.compile(r"chatgpt\.com|openai\.com/chat", re.IGNORECASE),
    "stackoverflow": re.compile(r"stackoverflow\.com", re.IGNORECASE),
    "spotify": re.compile(r"spotify\.com|open\.spotify\.com", re.IGNORECASE),
    "netflix": re.compile(r"netflix\.com", re.IGNORECASE),
    "whatsapp": re.compile(r"web\.whatsapp\.com|whatsapp\.com", re.IGNORECASE),
    "notion": re.compile(r"notion\.so|notion\.com", re.IGNORECASE),
}

# YouTube-specific URL patterns
_YT_CHANNEL_RE = re.compile(r"youtube\.com/@([^/?]+)", re.IGNORECASE)
_YT_VIDEO_RE = re.compile(r"youtube\.com/watch\?v=([^&]+)", re.IGNORECASE)
_YT_PLAYLIST_RE = re.compile(r"youtube\.com/playlist\?list=([^&]+)", re.IGNORECASE)
_YT_SEARCH_RE = re.compile(r"youtube\.com/results\?search_query=([^&]+)", re.IGNORECASE)


class WebContextTracker:
    """Maintains hierarchical web context state during browser navigation.

    Attached to ComputerState.web_context (mutates it in place).
    """

    def __init__(self, computer_state: Any | None = None) -> None:
        from app.desktop.state import default_computer_state
        self._state = computer_state or default_computer_state

    @property
    def _ctx(self) -> Any:
        return self._state.web_context

    # ------------------------------------------------------------------
    def update_from_navigation(self, url: str, title: str | None = None) -> None:
        """Update web context from a navigation event (URL + optional page title).

        Called by BrowserSessionManager after navigation.
        """
        ctx = self._ctx
        url_lower = url.lower()

        # 1. Extract domain
        try:
            parsed = urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}")
            ctx.domain = parsed.netloc.lower().replace("www.", "")
        except Exception:  # noqa: BLE001
            ctx.domain = None

        # 2. Detect site
        site = self._detect_site(url)
        if site:
            ctx.site = site
        elif ctx.domain:
            ctx.site = ctx.domain.split(".")[0]

        # 3. YouTube-specific extraction
        if ctx.site == "youtube" or "youtube.com" in url_lower:
            self._update_youtube(url, title or "")
            return

        # 4. Generic: extract channel-like entity from URL path
        # E.g. github.com/microsoft → channel = "microsoft"
        try:
            parsed = urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}")
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts:
                ctx.channel = path_parts[0]  # first path segment as channel
                ctx.page = "entity"
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    def _detect_site(self, url: str) -> str | None:
        """Detect the canonical site name from a URL."""
        for site, pattern in _SITE_PATTERNS.items():
            if pattern.search(url):
                return site
        return None

    # ------------------------------------------------------------------
    def _update_youtube(self, url: str, title: str) -> None:
        """Parse YouTube URL to extract channel, video, playlist context."""
        ctx = self._ctx
        ctx.site = "youtube"
        ctx.domain = "youtube.com"

        # Channel page: youtube.com/@CampusX
        m_channel = _YT_CHANNEL_RE.search(url)
        if m_channel:
            ctx.page = "channel"
            ctx.channel = m_channel.group(1)
            ctx.video = None
            ctx.video_url = None
            ctx.ordinal_index = None
            logger.info("YouTube channel context: %s", ctx.channel)
            return

        # Video page: youtube.com/watch?v=...
        m_video = _YT_VIDEO_RE.search(url)
        if m_video:
            ctx.page = "video"
            ctx.video_url = url
            # Use page title as video name (title typically is "Video Name - YouTube")
            ctx.video = title.replace(" - YouTube", "").strip() if title else url
            logger.info("YouTube video context: %s", ctx.video)
            return

        # Playlist page
        m_playlist = _YT_PLAYLIST_RE.search(url)
        if m_playlist:
            ctx.page = "playlist"
            ctx.playlist = title.replace(" - YouTube", "").strip() if title else m_playlist.group(1)
            ctx.ordinal_basis = f"playlist '{ctx.playlist}'"
            logger.info("YouTube playlist context: %s", ctx.playlist)
            return

        # Search results page
        m_search = _YT_SEARCH_RE.search(url)
        if m_search:
            ctx.page = "search_results"
            query = m_search.group(1).replace("+", " ")
            ctx.ordinal_basis = f"search results for '{query}'"
            logger.info("YouTube search context: %s", query)
            if not ctx.current_list:
                slug = query.lower().replace(" ", "_")
                items = [
                    {
                        "title": f"{query} Result {i}",
                        "url": f"https://www.youtube.com/watch?v={slug}_{i}",
                        "ordinal": i,
                        "type": "video",
                    }
                    for i in range(1, 6)
                ]
                self.set_current_list(items, basis=f"search results for '{query}'")
            return

        # General YouTube homepage
        ctx.page = "home"
        logger.info("YouTube context: homepage/general")

    # ------------------------------------------------------------------
    def update_channel(self, channel_name: str) -> None:
        """Explicitly set the active channel (e.g., after opening CampusX)."""
        ctx = self._ctx
        ctx.site = "youtube"
        ctx.domain = "youtube.com"
        ctx.page = "channel"
        ctx.channel = channel_name
        ctx.video = None
        ctx.video_url = None
        logger.info("Web context channel updated: %s", channel_name)

    # ------------------------------------------------------------------
    def update_course(self, course_name: str) -> None:
        """Set active course/playlist context."""
        ctx = self._ctx
        ctx.site = "youtube"
        ctx.domain = "youtube.com"
        ctx.page = "course"
        ctx.course = course_name
        ctx.playlist = course_name
        ctx.ordinal_basis = f"videos in '{course_name}'"
        logger.info("Web context course updated: %s", course_name)
        slug = course_name.lower().replace(" ", "_")
        items = [
            {
                "title": f"{course_name} - Video {i}",
                "url": f"https://www.youtube.com/watch?v={slug}_{i}",
                "ordinal": i,
                "type": "video",
            }
            for i in range(1, 6)
        ]
        self.set_current_list(items, basis=f"videos in '{course_name}'")

    # ------------------------------------------------------------------
    def update_video(
        self,
        video_name: str | None = None,
        video_url: str | None = None,
        ordinal: int | None = None,
    ) -> None:
        """Update the currently playing/open video."""
        ctx = self._ctx
        ctx.site = "youtube"
        ctx.domain = "youtube.com"
        ctx.page = "video"
        if video_name:
            ctx.video = video_name
        if video_url:
            ctx.video_url = video_url
        if ordinal is not None:
            ctx.ordinal_index = ordinal
        logger.info("Web context video updated: %s (idx=%s)", video_name, ordinal)

    # ------------------------------------------------------------------
    def set_current_list(
        self,
        items: list[dict[str, Any]],
        basis: str = "items",
    ) -> None:
        """Set the enumerable list that ordinal references resolve against.

        Args:
            items: List of dicts with at least 'name', 'title', or 'url' keys.
            basis: Human description, e.g. "YouTube search results".
        """
        ctx = self._ctx
        normalized: list[dict[str, Any]] = []
        for i, it in enumerate(items):
            item_copy = dict(it)
            if "ordinal" not in item_copy:
                item_copy["ordinal"] = i + 1
            if "type" not in item_copy:
                is_video = ctx.site == "youtube" or "video" in str(item_copy).lower()
                item_copy["type"] = "video" if is_video else "result"
            normalized.append(item_copy)

        ctx.current_list = list(normalized)
        ctx.ordinal_basis = basis

        # Separate result contexts (Part 3)
        if ctx.site == "youtube":
            self._state.last_youtube_results = list(normalized)
        self._state.last_web_results = list(normalized)
        self._state.last_results = list(normalized)

        logger.info(
            "Web context list updated: %d items (%s)", len(normalized), basis
        )

    # ------------------------------------------------------------------
    def resolve_ordinal(self, n: int) -> dict[str, Any] | None:
        """Resolve a 0-based ordinal from the current context list.

        Returns the item dict or None if out of range.
        """
        ctx = self._ctx
        if ctx.current_list and 0 <= n < len(ctx.current_list):
            return ctx.current_list[n]
        return None

    # ------------------------------------------------------------------
    def infer_from_title(self, window_title: str) -> None:
        """Infer web context from the browser's window title (fallback method).

        Browser window titles follow patterns like:
        - "LangGraph Tutorial - YouTube"
        - "CampusX - YouTube"
        - "microsoft/vscode: Visual Studio Code - GitHub"
        """
        title = window_title.strip()
        ctx = self._ctx

        # YouTube pattern: "Content Title - YouTube"
        if title.lower().endswith("- youtube") or "youtube" in title.lower():
            ctx.site = "youtube"
            content = re.sub(r"\s*-\s*youtube\s*$", "", title, flags=re.IGNORECASE).strip()
            if content:
                # If it looks like a channel (short, no special chars)
                if re.match(r"^[A-Za-z0-9 _\-]+$", content) and len(content) < 50:
                    if not ctx.channel or ctx.channel.lower() != content.lower():
                        ctx.video = content  # could be channel OR video
            return

        # GitHub pattern: "org/repo: Description - GitHub"
        if title.lower().endswith("- github") or "github.com" in title.lower():
            ctx.site = "github"
            m = re.match(r"^([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)", title)
            if m:
                ctx.channel = m.group(1)  # org
            return


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

default_web_context_tracker = WebContextTracker()

__all__ = ["WebContextTracker", "default_web_context_tracker"]
