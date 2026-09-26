"""Typed context tracking for the JARVIS Autonomous Computer Agent.

Guarantees:
1. No untyped bags of generic objects.
2. Grounded sources: Every entity must originate from an actual observation source
   (e.g., 'filesystem', 'browser_dom_cdp', 'os_window', 'browser_tab'). Zero fake items.
3. Strict ordinal and domain mapping for deictic references ('the third one', 'it', 'those').
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EntitySource = Literal[
    "filesystem",
    "browser_dom_cdp",
    "os_window",
    "browser_tab",
    "accessibility_tree",
]


@dataclass
class FileSystemEntity:
    """A real file or folder observed on the filesystem."""

    ordinal: int
    name: str
    path: str
    type: Literal["folder", "file"] = "folder"
    size_bytes: int | None = None
    modified_at: float | None = None
    source: EntitySource = "filesystem"
    observed_at: float = field(default_factory=time.time)

    @property
    def path_or_url(self) -> str:
        return self.path

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class YouTubeVideoEntity:
    """A real YouTube video result observed in the browser DOM."""

    ordinal: int
    title: str
    url: str
    channel: str | None = None
    duration: str | None = None
    type: Literal["video"] = "video"
    source: EntitySource = "browser_dom_cdp"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class YouTubeChannelEntity:
    """A real YouTube channel observed in the browser DOM."""

    ordinal: int
    title: str
    url: str
    channel_id: str | None = None
    type: Literal["channel"] = "channel"
    source: EntitySource = "browser_dom_cdp"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class YouTubePlaylistEntity:
    """A real YouTube playlist observed in the browser DOM."""

    ordinal: int
    title: str
    url: str
    video_count: int | None = None
    type: Literal["playlist"] = "playlist"
    source: EntitySource = "browser_dom_cdp"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class BrowserResultEntity:
    """A real web search or link result observed in the browser DOM."""

    ordinal: int
    title: str
    url: str
    snippet: str | None = None
    type: Literal["web_result", "link"] = "web_result"
    source: EntitySource = "browser_dom_cdp"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class GitHubResultEntity:
    """A real GitHub profile or repository observed in the browser DOM."""

    ordinal: int
    title: str
    url: str
    username: str | None = None
    repo_name: str | None = None
    type: Literal["github_user", "github_repo", "github_result"] = "github_result"
    source: EntitySource = "browser_dom_cdp"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.username or self.repo_name or self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class WindowEntity:
    """A real application window observed via Windows OS APIs."""

    ordinal: int
    title: str
    process_name: str
    window_id: str | None = None
    is_active: bool = False
    source: EntitySource = "os_window"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.process_name

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class BrowserTabEntity:
    """A real tab observed in the active browser session."""

    ordinal: int
    title: str
    url: str
    tab_id: str | None = None
    is_active: bool = False
    source: EntitySource = "browser_tab"
    observed_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.title

    @property
    def path_or_url(self) -> str:
        return self.url

    @property
    def timestamp(self) -> float:
        return self.observed_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["path_or_url"] = self.path_or_url
        d["timestamp"] = self.timestamp
        return d


@dataclass
class ActionRecord:
    """Structured audit trail of an executed tool action."""

    step_id: str
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    observation: str | dict[str, Any]
    verified: bool
    verification_evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TypedContext:
    """Task-scoped typed working memory for Computer Agent reasoning.

    Maintains distinct lists for each domain so 'open the third one' resolves
    against the active domain rather than mixing YouTube videos with folders.
    """

    filesystem_results: list[FileSystemEntity] = field(default_factory=list)
    youtube_video_results: list[YouTubeVideoEntity] = field(default_factory=list)
    youtube_channel_results: list[YouTubeChannelEntity] = field(default_factory=list)
    youtube_playlist_results: list[YouTubePlaylistEntity] = field(default_factory=list)
    browser_search_results: list[BrowserResultEntity] = field(default_factory=list)
    github_results: list[GitHubResultEntity] = field(default_factory=list)
    open_windows: list[WindowEntity] = field(default_factory=list)
    browser_tabs: list[BrowserTabEntity] = field(default_factory=list)
    recent_actions: list[ActionRecord] = field(default_factory=list)

    # Active focus pointers
    last_opened_folder: str | None = None
    last_opened_file: str | None = None
    last_active_domain: Literal["filesystem", "browser", "window", "unknown"] = "unknown"
    pending_action: dict[str, Any] | None = None
    folder_contents_cache: dict[str, list[FileSystemEntity]] = field(default_factory=dict)

    def clear_filesystem(self) -> None:
        self.filesystem_results.clear()

    def clear_browser(self) -> None:
        self.youtube_video_results.clear()
        self.youtube_channel_results.clear()
        self.youtube_playlist_results.clear()
        self.browser_search_results.clear()
        self.github_results.clear()
        self.browser_tabs.clear()

    def clear_all(self) -> None:
        self.filesystem_results.clear()
        self.youtube_video_results.clear()
        self.youtube_channel_results.clear()
        self.youtube_playlist_results.clear()
        self.browser_search_results.clear()
        self.github_results.clear()
        self.open_windows.clear()
        self.browser_tabs.clear()
        self.recent_actions.clear()
        self.folder_contents_cache.clear()
        self.last_opened_folder = None
        self.last_opened_file = None
        self.last_active_domain = "unknown"
        self.pending_action = None

    def restore_folder_entities(self, folder_path_or_name: str | None) -> bool:
        """Restore cached filesystem entities when navigating back into a folder."""
        if not folder_path_or_name:
            return False
        clean_key = (
            str(folder_path_or_name)
            .strip()
            .rstrip("/\\")
            .replace("\\", "/")
            .split("/")[-1]
            .lower()
        )
        if clean_key in self.folder_contents_cache:
            self.filesystem_results = list(self.folder_contents_cache[clean_key])
            self.clear_browser()
            self.last_active_domain = "filesystem"
            return True
        return False

    def set_filesystem_entities(
        self,
        items: list[dict[str, Any] | str],
        default_type: Literal["folder", "file"] = "file",
        base_dir: str | None = None,
    ) -> None:
        """Store observed filesystem entities, computing 1-based ordinals.

        Clears browser/YouTube context so active File Explorer context is not contaminated.
        """
        from pathlib import Path

        self.clear_browser()
        results: list[FileSystemEntity] = []
        for idx, it in enumerate(items):
            if isinstance(it, str):
                name = it
                target_base = base_dir or self.last_opened_folder or ""
                p = str(Path(target_base) / it) if target_base else it
                results.append(
                    FileSystemEntity(
                        ordinal=idx + 1,
                        name=name,
                        path=p,
                        type=default_type,
                        source="filesystem",
                    )
                )
            elif isinstance(it, dict):
                results.append(
                    FileSystemEntity(
                        ordinal=idx + 1,
                        name=it.get("name", ""),
                        path=it.get("path", ""),
                        type="folder" if it.get("is_dir", it.get("type") == "folder") else "file",
                        size_bytes=it.get("size"),
                        modified_at=it.get("modified"),
                        source="filesystem",
                    )
                )
        self.filesystem_results = results
        self.last_active_domain = "filesystem"

        # Cache folder contents under directory key
        target_dir = str(base_dir or self.last_opened_folder or "")
        dir_to_cache = (
            target_dir.strip().rstrip("/\\").replace("\\", "/").split("/")[-1].lower()
        )
        if dir_to_cache:
            self.folder_contents_cache[dir_to_cache] = list(results)

    def set_youtube_entities(self, items: list[dict[str, Any]]) -> None:
        """Store observed YouTube video entities from real DOM extraction."""
        self.youtube_video_results = [
            YouTubeVideoEntity(
                ordinal=idx + 1,
                title=it.get("title", ""),
                url=it.get("url", ""),
                channel=it.get("channel"),
                duration=it.get("duration"),
                source="browser_dom_cdp",
            )
            for idx, it in enumerate(items)
            if it.get("url")
        ]
        self.last_active_domain = "browser"

    def set_browser_search_entities(self, items: list[dict[str, Any]]) -> None:
        """Store observed browser web search entities."""
        self.browser_search_results = [
            BrowserResultEntity(
                ordinal=idx + 1,
                title=it.get("title", ""),
                url=it.get("url", ""),
                snippet=it.get("snippet"),
                source="browser_dom_cdp",
            )
            for idx, it in enumerate(items)
            if it.get("url")
        ]
        self.last_active_domain = "browser"

    def set_github_entities(self, items: list[dict[str, Any]]) -> None:
        """Store observed GitHub profile or repository entities from DOM extraction."""
        self.github_results = [
            GitHubResultEntity(
                ordinal=idx + 1,
                title=it.get("title", it.get("name", "")),
                url=it.get("url", ""),
                username=it.get("username"),
                repo_name=it.get("repo_name"),
                type=it.get("type", "github_result"),
                source="browser_dom_cdp",
            )
            for idx, it in enumerate(items)
            if it.get("url")
        ]
        self.last_active_domain = "browser"

    def resolve_ordinal(
        self,
        ordinal: int,
        preferred_domain: str | None = None,
    ) -> FileSystemEntity | YouTubeVideoEntity | BrowserResultEntity | GitHubResultEntity | None:
        """Resolve a 1-based ordinal reference ('the third one') based on active domain.

        Never resolves a filesystem ordinal to a YouTube video or vice versa.
        Strict domain separation prevents cross-contamination.
        """
        domain = preferred_domain or self.last_active_domain

        if domain == "filesystem":
            for item in self.filesystem_results:
                if item.ordinal == ordinal:
                    return item
            return None

        if domain in ("youtube", "browser"):
            for item in self.youtube_video_results:
                if item.ordinal == ordinal:
                    return item
            for item in self.browser_search_results:
                if item.ordinal == ordinal:
                    return item
            for item in self.github_results:
                if item.ordinal == ordinal:
                    return item
            return None

        if domain == "github":
            for item in self.github_results:
                if item.ordinal == ordinal:
                    return item
            return None

        if domain == "window":
            for item in self.open_windows:
                if item.ordinal == ordinal:
                    return item
            return None

        # Fallback to last active domain with strict boundary
        if self.last_active_domain == "filesystem":
            for item in self.filesystem_results:
                if item.ordinal == ordinal:
                    return item
            return None

        if self.last_active_domain == "browser":
            for item in self.youtube_video_results:
                if item.ordinal == ordinal:
                    return item
            for item in self.browser_search_results:
                if item.ordinal == ordinal:
                    return item
            for item in self.github_results:
                if item.ordinal == ordinal:
                    return item
            return None

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filesystem_results": [it.to_dict() for it in self.filesystem_results],
            "youtube_video_results": [it.to_dict() for it in self.youtube_video_results],
            "youtube_channel_results": [it.to_dict() for it in self.youtube_channel_results],
            "youtube_playlist_results": [it.to_dict() for it in self.youtube_playlist_results],
            "browser_search_results": [it.to_dict() for it in self.browser_search_results],
            "github_results": [it.to_dict() for it in self.github_results],
            "open_windows": [it.to_dict() for it in self.open_windows],
            "browser_tabs": [it.to_dict() for it in self.browser_tabs],
            "recent_actions": [it.to_dict() for it in self.recent_actions[-10:]],
            "last_opened_folder": self.last_opened_folder,
            "last_opened_file": self.last_opened_file,
            "last_active_domain": self.last_active_domain,
            "pending_action": self.pending_action,
        }
