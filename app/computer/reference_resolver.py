"""Contextual Reference Resolver for JARVIS Computer-Use Agent.

Resolves pronoun and ordinal references in user utterances by looking up
the current ComputerState context.

Supported references:
- "it", "that", "this"       → last_target
- "the first one"            → last_results[0] or web_context.current_list[0]
- "the third video"          → web_context.current_list[2]
- "the same browser"         → browser_specifically_requested or browser_name
- "the current page"         → active_page_url
- "it" (in file context)     → last_search_results[0] if only one result
- Ordinals without context   → web_context.current_list[n] (if populated)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ordinal map: spoken form → 0-based index
# ---------------------------------------------------------------------------
ORDINAL_MAP: dict[str, int] = {
    "first": 0, "1st": 0, "one": 0,
    "second": 1, "2nd": 1, "two": 1,
    "third": 2, "3rd": 2, "three": 2,
    "fourth": 3, "4th": 3, "four": 3,
    "fifth": 4, "5th": 4, "five": 4,
    "sixth": 5, "6th": 5,
    "seventh": 6, "7th": 6,
    "eighth": 7, "8th": 7,
    "ninth": 8, "9th": 8,
    "tenth": 9, "10th": 9,
}

_ORDINAL_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\b",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(r"\b(it|that|this)\b", re.IGNORECASE)
_SAME_BROWSER_RE = re.compile(
    r"\b(same\s+browser|current\s+browser|that\s+browser)\b", re.IGNORECASE
)
_CURRENT_PAGE_RE = re.compile(
    r"\b(current\s+page|this\s+page|that\s+page|this\s+tab)\b", re.IGNORECASE
)
_THERE_RE = re.compile(r"\b(there|in\s+there)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass
class ResolvedReference:
    """Result of resolving a contextual reference."""

    resolved: bool
    kind: str                      # "url", "file", "browser", "app", "web_entity", "video"
    # explicit reference type: "video", "file", "result", "browser", "destination"
    type: str | None = None
    ordinal: int | None = None     # 1-based ordinal
    value: str | None = None       # The concrete resolved value (URL, path, name)
    metadata: dict[str, Any] | None = None
    reason: str = ""


class ReferenceResolver:
    """Resolves contextual references in computer-control utterances.

    The resolver inspects ComputerState fields in priority order:
    1. web_context.current_list (YouTube/site entity list)
    2. last_results (general enumerable list)
    3. last_search_results (filesystem search results)
    4. last_target (last explicitly named entity)
    5. active_page_url (current page)
    6. browser_specifically_requested / browser_name
    """

    # ------------------------------------------------------------------
    def resolve_ordinal(
        self,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference | None:
        """Extract and resolve an ordinal reference from the utterance.

        Returns None if no ordinal is found in the text.
        """
        m = _ORDINAL_RE.search(text.lower())
        if not m:
            return None

        idx = ORDINAL_MAP.get(m.group(0).lower(), 0)
        return self._resolve_index(idx, text, computer_state)

    # ------------------------------------------------------------------
    def resolve_pronoun(
        self,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference | None:
        """Resolve pronoun references ("it", "that", "this").

        Returns None if no pronoun detected or nothing to resolve against.
        """
        if not _PRONOUN_RE.search(text):
            return None

        # 1. Try last_target (most recent explicitly named thing)
        last_target = getattr(computer_state, "last_target", None)
        if last_target:
            return ResolvedReference(
                resolved=True,
                kind="app",
                value=last_target,
                reason=f"pronoun resolved to last_target: '{last_target}'",
            )

        # 2. Try single last_results
        last_results = getattr(computer_state, "last_results", [])
        if len(last_results) == 1:
            item = last_results[0]
            val = item.get("url") or item.get("path") or item.get("name") or str(item)
            return ResolvedReference(
                resolved=True,
                kind="result",
                value=val,
                metadata=item,
                reason="pronoun resolved to single last_result",
            )

        # 3. Try single last_search_results
        last_fs = getattr(computer_state, "last_search_results", [])
        if len(last_fs) == 1:
            item = last_fs[0]
            val = item.get("path") or item.get("name") or str(item)
            return ResolvedReference(
                resolved=True,
                kind="file",
                value=val,
                metadata=item,
                reason="pronoun resolved to single last_search_result",
            )

        # 4. Try active page URL
        url = getattr(computer_state, "active_page_url", None) or \
              getattr(computer_state, "current_url", None)
        if url:
            return ResolvedReference(
                resolved=True,
                kind="url",
                value=url,
                reason=f"pronoun resolved to current page URL: '{url}'",
            )

        return ResolvedReference(
            resolved=False,
            kind="unknown",
            reason="pronoun found but no context to resolve against",
        )

    # ------------------------------------------------------------------
    def resolve_browser_reference(
        self,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference | None:
        """Resolve references to 'the same browser' or 'current browser'."""
        if not _SAME_BROWSER_RE.search(text):
            return None

        browser = (
            getattr(computer_state, "browser_specifically_requested", None)
            or getattr(computer_state, "browser_name", None)
        )
        if browser:
            return ResolvedReference(
                resolved=True,
                kind="browser",
                value=browser,
                reason=f"browser reference resolved to '{browser}'",
            )

        return ResolvedReference(
            resolved=False,
            kind="browser",
            reason="no active browser in context",
        )

    # ------------------------------------------------------------------
    def resolve_current_page(
        self,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference | None:
        """Resolve 'current page', 'this tab', etc."""
        if not _CURRENT_PAGE_RE.search(text):
            return None

        url = getattr(computer_state, "active_page_url", None) or \
              getattr(computer_state, "current_url", None)
        if url:
            return ResolvedReference(
                resolved=True,
                kind="url",
                value=url,
                reason=f"current page resolved to '{url}'",
            )

        return ResolvedReference(
            resolved=False,
            kind="url",
            reason="no active page URL in context",
        )

    # ------------------------------------------------------------------
    def resolve_there(
        self,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference | None:
        """Resolve 'there' based on current navigation or directory context."""
        if not _THERE_RE.search(text):
            return None

        wc = getattr(computer_state, "web_context", None)
        if wc and wc.site:
            loc = wc.course or wc.channel or wc.site
            return ResolvedReference(
                resolved=True,
                kind="web_context",
                type="destination",
                value=loc,
                reason=f"'there' resolved to web context: {loc}",
            )

        url = (
            getattr(computer_state, "active_page_url", None)
            or getattr(computer_state, "current_url", None)
        )
        if url:
            return ResolvedReference(
                resolved=True,
                kind="url",
                type="destination",
                value=url,
                reason=f"'there' resolved to active URL: {url}",
            )

        curr_dir = getattr(computer_state, "current_directory", None)
        if curr_dir:
            return ResolvedReference(
                resolved=True,
                kind="folder",
                type="destination",
                value=curr_dir,
                reason=f"'there' resolved to current directory: {curr_dir}",
            )

        return ResolvedReference(
            resolved=False,
            kind="destination",
            type="destination",
            reason="'there' detected but no active navigation or directory context",
        )

    # ------------------------------------------------------------------
    def resolve_all(
        self,
        text: str,
        computer_state: Any,
    ) -> list[ResolvedReference]:
        """Attempt all reference types and return resolved ones."""
        results: list[ResolvedReference] = []

        r = self.resolve_ordinal(text, computer_state)
        if r is not None:
            results.append(r)

        r = self.resolve_pronoun(text, computer_state)
        if r is not None:
            results.append(r)

        r = self.resolve_browser_reference(text, computer_state)
        if r is not None:
            results.append(r)

        r = self.resolve_current_page(text, computer_state)
        if r is not None:
            results.append(r)

        r = self.resolve_there(text, computer_state)
        if r is not None:
            results.append(r)

        return results

    # ------------------------------------------------------------------
    def _resolve_index(
        self,
        idx: int,
        text: str,
        computer_state: Any,
    ) -> ResolvedReference:
        """Resolve a 0-based index against available context lists with contextual priority.

        Part 4 Priority rules:
        - For 'third video' or video context:
          1. current web context (web_context.current_list)
          2. current YouTube list (last_youtube_results)
          3. previous compatible web result (last_web_results)
          DO NOT search filesystem state.
        - For 'first file' or file context:
          1. last_files
          2. last_search_results
          DO NOT search YouTube/web.
        - For generic ordinals ("the first one"):
          Resolve based on current compatible result set.
        """
        lower = text.lower()

        # Determine what kind of entity is explicitly requested
        is_video = any(k in lower for k in ("video", "clip", "lesson", "stream", "track"))
        is_folder = any(k in lower for k in ("folder", "directory", "dir"))
        is_file = any(k in lower for k in ("file", "document", "pdf", "sheet", "item in folder"))
        is_next = "next" in lower or "subsequent" in lower

        wc = getattr(computer_state, "web_context", None)
        active_site = getattr(wc, "site", None) if wc else None

        # Relative navigation: "Open the next video"
        if is_next and wc and wc.ordinal_index is not None:
            idx = wc.ordinal_index + 1

        target_type = "video" if is_video else ("folder" if is_folder else ("file" if is_file else None))
        if target_type is None:
            # Check active application and last action first:
            active_app = (getattr(computer_state, "active_application", None) or "").lower()
            last_action = getattr(computer_state, "last_action", "") or ""
            is_fs_active = (
                "explorer" in active_app
                or last_action in ("count_directory_items", "list_directory", "open_folder", "search_files")
            )

            if is_fs_active and (
                getattr(computer_state, "last_files", None)
                or getattr(computer_state, "last_search_results", None)
                or getattr(computer_state, "last_results", None)
            ):
                target_type = "file"
            elif active_site == "youtube" or (wc and wc.current_list):
                target_type = "video"
            elif (
                getattr(computer_state, "last_search_results", None)
                or getattr(computer_state, "last_files", None)
                or getattr(computer_state, "last_results", None)
            ):
                target_type = "file"
            else:
                target_type = "generic"

        # --------------------------------------------------------------
        # PRIORITY 1: VIDEO TYPE
        # --------------------------------------------------------------
        if target_type == "video":
            # 1. web_context.current_list
            if wc and wc.current_list:
                if 0 <= idx < len(wc.current_list):
                    item = wc.current_list[idx]
                    val = (
                        item.get("url")
                        or item.get("link")
                        or item.get("title")
                        or item.get("name")
                        or str(item)
                    )
                    basis = wc.ordinal_basis or "videos"
                    return ResolvedReference(
                        resolved=True,
                        kind="video",
                        type="video",
                        ordinal=idx + 1,
                        value=val,
                        metadata=item,
                        reason=(
                            f"ordinal [{idx + 1}] resolved from "
                            f"web_context.current_list ({basis})"
                        ),
                    )
                return ResolvedReference(
                    resolved=False,
                    kind="video",
                    type="video",
                    ordinal=idx + 1,
                    reason=(
                        f"video [{idx + 1}] out of range: "
                        f"web_context has {len(wc.current_list)} videos"
                    ),
                )

            # 2. last_youtube_results
            yt_res = getattr(computer_state, "last_youtube_results", [])
            if yt_res:
                if 0 <= idx < len(yt_res):
                    item = yt_res[idx]
                    val = item.get("url") or item.get("title") or str(item)
                    return ResolvedReference(
                        resolved=True,
                        kind="video",
                        type="video",
                        ordinal=idx + 1,
                        value=val,
                        metadata=item,
                        reason=f"ordinal [{idx + 1}] resolved from last_youtube_results",
                    )
                return ResolvedReference(
                    resolved=False,
                    kind="video",
                    type="video",
                    ordinal=idx + 1,
                    reason=(
                        f"video [{idx + 1}] out of range: "
                        f"last_youtube_results has {len(yt_res)} items"
                    ),
                )

            # 3. last_web_results
            web_res = getattr(computer_state, "last_web_results", [])
            if web_res:
                if 0 <= idx < len(web_res):
                    item = web_res[idx]
                    val = item.get("url") or item.get("title") or str(item)
                    return ResolvedReference(
                        resolved=True,
                        kind="video",
                        type="video",
                        ordinal=idx + 1,
                        value=val,
                        metadata=item,
                        reason=f"ordinal [{idx + 1}] resolved from last_web_results",
                    )

            # CRITICAL: DO NOT search filesystem state for video!
            return ResolvedReference(
                resolved=False,
                kind="video",
                type="video",
                ordinal=idx + 1,
                reason=f"video [{idx + 1}] requested but no web or YouTube videos in context",
            )

        # --------------------------------------------------------------
        # PRIORITY 2: FILE / FOLDER TYPE
        # --------------------------------------------------------------
        if target_type in ("file", "folder"):
            # 1. last_results (general enumerable context)
            last_res = getattr(computer_state, "last_results", [])
            if last_res and 0 <= idx < len(last_res):
                item = last_res[idx]
                if isinstance(item, dict):
                    val = item.get("path") or item.get("name") or str(item)
                    item_kind = "folder" if item.get("type") == "folder" or item.get("is_dir") else "file"
                    meta = item
                else:
                    val = str(item)
                    item_kind = "file"
                    meta = {"name": val, "path": val}
                return ResolvedReference(
                    resolved=True,
                    kind=item_kind,
                    type=item_kind,
                    ordinal=idx + 1,
                    value=val,
                    metadata=meta,
                    reason=f"ordinal [{idx + 1}] resolved from last_results",
                )

            # 2. last_files
            last_files = getattr(computer_state, "last_files", [])
            if last_files and 0 <= idx < len(last_files):
                item = last_files[idx]
                if isinstance(item, dict):
                    val = item.get("path") or item.get("name") or str(item)
                    item_kind = "folder" if item.get("type") == "folder" or item.get("is_dir") else "file"
                    meta = item
                else:
                    val = str(item)
                    item_kind = "file"
                    meta = {"name": val, "path": val}
                return ResolvedReference(
                    resolved=True,
                    kind=item_kind,
                    type=item_kind,
                    ordinal=idx + 1,
                    value=val,
                    metadata=meta,
                    reason=f"ordinal [{idx + 1}] resolved from last_files",
                )

            # 3. last_search_results
            last_fs = getattr(computer_state, "last_search_results", [])
            if last_fs and 0 <= idx < len(last_fs):
                item = last_fs[idx]
                if isinstance(item, dict):
                    val = item.get("path") or item.get("name") or str(item)
                    item_kind = "folder" if item.get("type") == "folder" or item.get("is_dir") else "file"
                    meta = item
                else:
                    val = str(item)
                    item_kind = "file"
                    meta = {"name": val, "path": val}
                return ResolvedReference(
                    resolved=True,
                    kind=item_kind,
                    type=item_kind,
                    ordinal=idx + 1,
                    value=val,
                    metadata=meta,
                    reason=f"ordinal [{idx + 1}] resolved from last_search_results",
                )

            return ResolvedReference(
                resolved=False,
                kind=target_type,
                type=target_type,
                ordinal=idx + 1,
                reason=f"{target_type} [{idx + 1}] requested but no filesystem results available",
            )

        # --------------------------------------------------------------
        # PRIORITY 3: GENERIC / COMPATIBLE RESULT SET
        # --------------------------------------------------------------
        # Check web_context.current_list first if web was active
        if wc and wc.current_list and 0 <= idx < len(wc.current_list):
            item = wc.current_list[idx]
            val = (
                item.get("url")
                or item.get("path")
                or item.get("title")
                or item.get("name")
                or str(item)
            )
            return ResolvedReference(
                resolved=True,
                kind="web_entity",
                type="result",
                ordinal=idx + 1,
                value=val,
                metadata=item,
                reason=f"ordinal [{idx + 1}] resolved from web_context.current_list",
            )

        # Check last_results
        last_results = getattr(computer_state, "last_results", [])
        if last_results and 0 <= idx < len(last_results):
            item = last_results[idx]
            val = item.get("url") or item.get("path") or item.get("name") or str(item)
            return ResolvedReference(
                resolved=True,
                kind="result",
                type="result",
                ordinal=idx + 1,
                value=val,
                metadata=item,
                reason=f"ordinal [{idx + 1}] resolved from last_results",
            )

        # Check filesystem
        last_fs = getattr(computer_state, "last_search_results", [])
        if last_fs and 0 <= idx < len(last_fs):
            item = last_fs[idx]
            val = item.get("path") or item.get("name") or str(item)
            return ResolvedReference(
                resolved=True,
                kind="file",
                type="file",
                ordinal=idx + 1,
                value=val,
                metadata=item,
                reason=f"ordinal [{idx + 1}] resolved from last_search_results",
            )

        return ResolvedReference(
            resolved=False,
            kind="unknown",
            type="unknown",
            ordinal=idx + 1,
            reason=f"ordinal [{idx + 1}] requested but no enumerable context available",
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

default_resolver = ReferenceResolver()

__all__ = [
    "ReferenceResolver",
    "ResolvedReference",
    "ORDINAL_MAP",
    "default_resolver",
]
