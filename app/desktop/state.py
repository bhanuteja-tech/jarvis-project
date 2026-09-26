"""Central state management for desktop, application, and browser context.

Maintains authoritative knowledge of active application, window, process,
browser sessions, active pages/tabs, filesystem directory, tasks, and verifications
so follow-up commands execute coherently within the existing context.

Phase 8+: Extended with WebContext (YouTube/site hierarchical state), last_results
(general enumerable context for reference resolution), and browser_specifically_requested
(ensures the user-named browser is never silently substituted).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WebContext:
    """Hierarchical web context tracking for sites like YouTube.

    Tracks the current site, channel, course, video, and any enumerable
    list the user can refer back to with ordinal phrases like 'the third one'.
    """

    site: str | None = None            # e.g. "youtube", "github", "reddit"
    domain: str | None = None          # e.g. "youtube.com"
    # e.g. "search_results", "channel", "playlist", "course", "video"
    page: str | None = None
    channel: str | None = None         # e.g. "CampusX"
    playlist: str | None = None        # playlist or course name
    course: str | None = None          # specific course (subset of playlist)
    video: str | None = None           # current video title
    video_url: str | None = None       # current video URL
    ordinal_index: int | None = None   # 0-based index in current_list
    current_list: list[dict[str, Any]] = field(default_factory=list)
    ordinal_basis: str | None = None   # what the list represents ("videos", "results")

    def clear(self) -> None:
        """Reset all web context fields."""
        self.site = None
        self.domain = None
        self.page = None
        self.channel = None
        self.playlist = None
        self.course = None
        self.video = None
        self.video_url = None
        self.ordinal_index = None
        self.current_list.clear()
        self.ordinal_basis = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "domain": self.domain,
            "page": self.page,
            "channel": self.channel,
            "playlist": self.playlist,
            "course": self.course,
            "video": self.video,
            "video_url": self.video_url,
            "ordinal_index": self.ordinal_index,
            "current_list": list(self.current_list),
            "ordinal_basis": self.ordinal_basis,
        }



@dataclass
class DesiredState:
    """Intended postcondition state of a planned agent action."""

    action: str
    target: str = ""
    expected_app: str | None = None
    expected_url: str | None = None
    expected_directory: str | None = None
    expected_page: str | None = None
    expected_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ObservedState:
    """Raw observations captured from live OS, windows, filesystem, or browser DOM."""

    active_application: str | None = None
    active_window_title: str | None = None
    active_process: str | None = None
    current_directory: str | None = None
    active_page_url: str | None = None
    active_page_title: str | None = None
    browser_name: str | None = None
    observed_items: list[Any] = field(default_factory=list)
    raw_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerifiedState:
    """Authoritative state certified by Verifier comparing DesiredState against ObservedState."""

    task_id: str | None = None
    generation: int = 0
    is_verified: bool = False
    action: str = ""
    target: str = ""
    verified_app: str | None = None
    verified_directory: str | None = None
    verified_url: str | None = None
    verified_page: str | None = None
    verified_items: list[Any] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComputerState:
    """Authoritative context of the user's computer session."""

    # Generation Tracking (protects against stale task execution/state commits)
    current_generation: int = 0

    # Active Application / Window / Process
    active_application: str | None = None
    active_process: str | None = None
    active_window_id: str | None = None
    active_window_title: str | None = None

    # Browser Session Context
    browser_name: str | None = None  # e.g. "google_chrome", "microsoft_edge"
    browser: str | None = None  # display name / legacy alias
    browser_process: str | None = None
    browser_window_id: str | None = None
    browser_context_id: str | None = None
    active_page_id: str | None = None
    active_page_url: str | None = None
    active_page_title: str | None = None
    active_tab: str | None = None  # legacy alias
    current_url: str | None = None  # legacy alias
    open_pages: list[dict[str, Any]] = field(default_factory=list)

    # Filesystem Context
    current_directory: str = field(default_factory=lambda: str(Path.home() / "Desktop"))
    selected_file: str | None = None
    open_files: list[str] = field(default_factory=list)
    last_files: list[dict[str, Any]] = field(default_factory=list)
    last_search_results: list[dict[str, Any]] = field(default_factory=list)

    # Web & Application Result Contexts (Part 3)
    last_web_results: list[dict[str, Any]] = field(default_factory=list)
    last_youtube_results: list[dict[str, Any]] = field(default_factory=list)
    last_ui_elements: list[dict[str, Any]] = field(default_factory=list)

    # Task & Execution Context
    current_task_id: str | None = None
    current_step_id: str | None = None
    current_intent: str | None = None
    last_user_command: str | None = None
    last_intent: str | None = None
    last_target: str | None = None

    # Closed-Loop Observation & Verification
    last_action: str | None = None
    last_action_result: dict[str, Any] | None = None
    last_observation: str | None = None
    last_verification: dict[str, Any] | None = None

    # Side-Effect Safety & Confirmation
    pending_confirmation: dict[str, Any] | None = None
    pending_action: dict[str, Any] | None = None  # high-risk action awaiting user approval

    # Conversation Context
    conversation_context: dict[str, Any] = field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Semantic Computer-Use Agent Extensions (Phase 8+)
    # -----------------------------------------------------------------------

    # Web Context: hierarchical site/channel/course/video state
    web_context: WebContext = field(default_factory=WebContext)

    # General enumerable last results — any context user can refer to with
    # ordinals ("the third one", "the first video", "open it")
    # Supersedes the filesystem-only last_search_results for cross-domain use.
    last_results: list[dict[str, Any]] = field(default_factory=list)

    # When the user explicitly names a browser ("Open Edge", "use Chrome"),
    # store it here so subsequent navigation uses the SAME browser without
    # silently substituting the system default.
    browser_specifically_requested: str | None = None

    # Semantic verification fields
    last_verified: bool = False       # whether last action was independently verified
    last_verify_method: str | None = None  # how verification was done
    last_verify_reason: str | None = None

    def commit_verified_state(self, verified: VerifiedState) -> bool:
        """Authoritatively commit state ONLY after verification succeeds.

        Rejects stale generations and unverified state transitions.
        Ensures strict domain consistency (e.g. clearing web context on File Explorer navigation).
        """
        if verified.generation < self.current_generation:
            return False

        if not verified.is_verified:
            return False

        self.last_verified = True
        self.last_verification = verified.to_dict()
        self.last_verify_reason = verified.reason

        if verified.verified_app:
            self.active_application = verified.verified_app
            app_lower = verified.verified_app.lower()
            if "explorer" in app_lower or "desktop" in app_lower or app_lower == "file explorer":
                # Ground-truth: User navigated to OS filesystem; clear stale web context
                self.web_context.clear()
                self.browser_specifically_requested = None

        if verified.verified_directory:
            self.current_directory = verified.verified_directory

        if verified.verified_url:
            self.active_page_url = verified.verified_url
            self.current_url = verified.verified_url

        if verified.verified_page and self.web_context.site:
            self.web_context.page = verified.verified_page

        if verified.verified_items:
            self.last_results = list(verified.verified_items)
            if self.web_context.site:
                self.web_context.current_list = list(verified.verified_items)

        return True

    def update(self, **kwargs: Any) -> None:
        """Update state fields safely with bidirectional alias syncing."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # Sync browser aliases
        if "browser_name" in kwargs and kwargs["browser_name"]:
            self.browser = kwargs["browser_name"]
        elif "browser" in kwargs and kwargs["browser"]:
            self.browser_name = kwargs["browser"]

        # Sync URL aliases
        if "active_page_url" in kwargs and kwargs["active_page_url"]:
            self.current_url = kwargs["active_page_url"]
        elif "current_url" in kwargs and kwargs["current_url"]:
            self.active_page_url = kwargs["current_url"]

        # Sync intent aliases
        if "current_intent" in kwargs and kwargs["current_intent"]:
            self.last_intent = kwargs["current_intent"]
        elif "last_intent" in kwargs and kwargs["last_intent"]:
            self.current_intent = kwargs["last_intent"]

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for event envelopes and UI inspection."""
        return asdict(self)

    def reset(self) -> None:
        """Reset computer context to initial defaults."""
        self.current_generation = 0
        self.active_application = None
        self.active_process = None
        self.active_window_id = None
        self.active_window_title = None

        self.browser_name = None
        self.browser = None
        self.browser_process = None
        self.browser_window_id = None
        self.browser_context_id = None
        self.active_page_id = None
        self.active_page_url = None
        self.active_page_title = None
        self.active_tab = None
        self.current_url = None
        self.open_pages.clear()

        self.current_directory = str(Path.home() / "Desktop")
        self.selected_file = None
        self.open_files.clear()
        self.last_files.clear()
        self.last_search_results.clear()
        self.last_web_results.clear()
        self.last_youtube_results.clear()
        self.last_ui_elements.clear()

        self.current_task_id = None
        self.current_step_id = None
        self.current_intent = None
        self.last_user_command = None
        self.last_intent = None
        self.last_target = None

        self.last_action = None
        self.last_action_result = None
        self.last_observation = None
        self.last_verification = None

        self.pending_confirmation = None
        self.pending_action = None
        self.conversation_context.clear()
        self.web_context.clear()
        self.last_results.clear()
        self.browser_specifically_requested = None
        self.last_verified = False
        self.last_verify_method = None
        self.last_verify_reason = None


# Global singleton computer state
default_computer_state = ComputerState()
default_state = default_computer_state

__all__ = [
    "WebContext",
    "DesiredState",
    "ObservedState",
    "VerifiedState",
    "ComputerState",
    "default_computer_state",
    "default_state",
]
