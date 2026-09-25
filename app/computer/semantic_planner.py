"""Semantic Task Planner for JARVIS Computer-Use Agent.

Converts a ComputerIntent into an ordered list of typed TaskSteps,
each with:
- A concrete tool name + parameters
- An expected postcondition (what must be true after execution)
- A verification strategy (how to check success)

Planner rules:
- Multi-step intents are decomposed in dependency order
- Browser steps precede navigation steps (browser must be open first)
- High-risk actions (send message) get a confirmation step inserted before them
- Never generates steps for unresolvable references; fails cleanly
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import quote_plus

from app.computer.intent_extractor import (
    ApplicationTarget,
    ComputerIntent,
    _resolve_app_canonical,
)
from app.computer.reference_resolver import ReferenceResolver, default_resolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task Step
# ---------------------------------------------------------------------------

class VerificationStrategy(StrEnum):
    WINDOW_FOREGROUND = "window_foreground"     # check active window title
    BROWSER_FOREGROUND = "browser_foreground"   # check browser window is foreground
    URL_TITLE_POLL = "url_title_poll"           # poll window title for domain
    FILESYSTEM_DIRECTORY = "filesystem_dir"     # check current_directory
    SEARCH_URL = "search_url"                   # check URL contains search query
    WINDOW_CONTENT = "window_content"           # check window title contains text
    NONE = "none"                               # no verification (fast actions)
    CONFIRMATION_REQUIRED = "confirmation"      # user must confirm before proceeding


@dataclass
class TaskStep:
    """A single executable step in a computer-use plan.

    Attributes:
        step_id: Unique step identifier (e.g., "step_1")
        tool: The AgentHarness tool to call (e.g., "open_application", "navigate_browser")
        params: Parameters for the tool call
        description: Human-readable description for narration
        verification: How to verify success after execution
        verification_target: What to check (app name, URL domain, folder name)
        is_high_risk: If True, requires user confirmation before execution
        requires_previous: If True, must only run after previous step succeeds
        skip_if_already: Condition string for short-circuiting (e.g., "browser_open")
    """

    step_id: str
    tool: str
    params: dict[str, Any]
    description: str
    verification: VerificationStrategy = VerificationStrategy.NONE
    verification_target: str | None = None
    is_high_risk: bool = False
    requires_previous: bool = False
    skip_if_already: str | None = None
    expected_state_updates: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    """An ordered sequence of TaskSteps to execute for a ComputerIntent."""

    intent: ComputerIntent
    steps: list[TaskStep]
    description: str = ""
    requires_resolution: bool = False     # True if a reference couldn't be fully resolved
    resolution_error: str | None = None   # description of what couldn't be resolved

    @property
    def is_single_step(self) -> bool:
        return len(self.steps) == 1

    @property
    def has_high_risk_steps(self) -> bool:
        return any(s.is_high_risk for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "steps": [
                {
                    "step_id": s.step_id,
                    "tool": s.tool,
                    "params": s.params,
                    "description": s.description,
                    "verification": s.verification.value,
                    "verification_target": s.verification_target,
                    "is_high_risk": s.is_high_risk,
                }
                for s in self.steps
            ],
        }


# ---------------------------------------------------------------------------
# Service URL map
# ---------------------------------------------------------------------------

_SERVICE_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
    "reddit": "https://www.reddit.com",
    "stackoverflow": "https://stackoverflow.com",
    "leetcode": "https://leetcode.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "vercel": "https://vercel.com",
    "wikipedia": "https://en.wikipedia.org",
    "whatsapp": "https://web.whatsapp.com",
}

_SEARCH_URL_TEMPLATES: dict[str, str] = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "yt": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={query}",
}


def _build_search_url(service: str, query: str) -> str:
    """Build a search URL for a service and query."""
    from urllib.parse import quote_plus
    tmpl = _SEARCH_URL_TEMPLATES.get(service.lower())
    if tmpl:
        return tmpl.format(query=quote_plus(query))
    # Generic: try google
    from urllib.parse import quote_plus
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _get_service_url(service: str) -> str | None:
    """Return the homepage URL for a known web service."""
    return _SERVICE_URLS.get(service.lower())


def _get_service_domain(service: str, url: str | None = None) -> str:
    """Return the domain fragment for window-title verification."""
    known = {
        "youtube": "youtube.com",
        "yt": "youtube.com",
        "github": "github.com",
        "linkedin": "linkedin.com",
        "twitter": "twitter.com",
        "gmail": "gmail",
        "google": "google.com",
        "chatgpt": "chatgpt.com",
        "reddit": "reddit.com",
        "stackoverflow": "stackoverflow.com",
        "spotify": "spotify.com",
        "netflix": "netflix.com",
        "whatsapp": "whatsapp",
    }
    if service.lower() in known:
        return known[service.lower()]
    if url:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except Exception:  # noqa: BLE001
            pass
    return service.lower()


# ---------------------------------------------------------------------------
# SemanticTaskPlanner
# ---------------------------------------------------------------------------

class SemanticTaskPlanner:
    """Converts a ComputerIntent into a typed, ordered TaskPlan.

    This class only does PLANNING — it never calls tools.
    The ComputerAgent is responsible for execution.
    """

    def __init__(
        self,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        self._resolver = reference_resolver or default_resolver

    # ------------------------------------------------------------------
    def plan(
        self,
        intent: ComputerIntent,
        computer_state: Any | None = None,
    ) -> TaskPlan:
        """Convert intent to an executable TaskPlan.

        Args:
            intent: The structured intent from ComputerIntentExtractor.
            computer_state: Current ComputerState for context-aware planning.

        Returns:
            TaskPlan with ordered steps.
        """
        logger.info(
            "Planning for intent_type=%s, actions=%s",
            intent.intent_type,
            intent.actions,
        )

        # Dispatch to typed planner methods
        itype = intent.intent_type.upper()

        if itype == "OPEN_APPLICATION":
            return self._plan_open_application(intent, computer_state)

        if itype == "CLOSE_APPLICATION":
            return self._plan_close_application(intent, computer_state)

        if itype in ("BROWSER_NAVIGATE", "NAVIGATE_WEBSITE", "OPEN_WEBSITE", "OPEN_CHANNEL"):
            return self._plan_browser_navigate(intent, computer_state)

        if itype == "BROWSER_SEARCH":
            return self._plan_browser_search(intent, computer_state)

        if itype == "MESSAGING_SEND":
            return self._plan_messaging_send(intent, computer_state)

        if itype == "SCREEN_READ":
            return self._plan_screen_read(intent, computer_state)

        if itype in ("SELECT_ITEM", "OPEN_REFERENCE", "SELECT_RESULT"):
            return self._plan_select_item(intent, computer_state)

        if itype in ("OPEN_CONTENT", "OPEN_COURSE", "OPEN_PLAYLIST", "OPEN_VIDEO", "OPEN_RESULT"):
            return self._plan_open_content(intent, computer_state)

        if itype == "SCROLL":
            return self._plan_scroll(intent, computer_state)

        if itype == "CLICK":
            return self._plan_click(intent, computer_state)

        if itype in ("LIST_FILES", "OPEN_FILE", "SEARCH_FILES"):
            return self._plan_file_operation(intent, computer_state)

        if itype in ("OPEN_FOLDER", "NAVIGATE_FOLDER", "NAVIGATE_FILESYSTEM"):
            return self._plan_open_folder(intent, computer_state)

        if itype == "MULTI_STEP":
            return self._plan_multi_step(intent, computer_state)

        # Ambiguous or unknown commands require clarification — NEVER search Google!
        prompt = intent.clarification_prompt or "I need to know what you want me to open. Could you specify?"
        return TaskPlan(
            intent=intent,
            steps=[],
            description="Clarification required",
            requires_resolution=True,
            resolution_error=prompt,
        )

    # ------------------------------------------------------------------
    def _plan_open_application(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        app = intent.application
        if not app:
            # Try to extract from raw text
            canonical = _resolve_app_canonical(intent.raw_text)
            app = ApplicationTarget(name=intent.raw_text, canonical=canonical)

        canonical = app.canonical
        is_browser = app.is_browser or canonical in (
            "google_chrome", "microsoft_edge", "firefox", "brave", "opera"
        )

        # Check if browser already open → skip open, just focus
        browser_already_open = False
        if state and is_browser:
            current_browser = getattr(state, "browser_name", None)
            browser_already_open = (
                bool(current_browser)
                and canonical == current_browser
                and bool(getattr(state, "browser_window_id", None))
            )

        if is_browser and browser_already_open:
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="focus_browser",
                        params={"browser_name": canonical},
                        description=f"Focus {app.name}",
                        verification=VerificationStrategy.BROWSER_FOREGROUND,
                        verification_target=canonical,
                        skip_if_already="browser_focused",
                        expected_state_updates={"browser_specifically_requested": canonical},
                    )
                ],
                description=f"Focus {app.name} (already open)",
            )

        if is_browser:
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="open_browser",
                        params={"browser_name": canonical},
                        description=f"Open {app.name}",
                        verification=VerificationStrategy.BROWSER_FOREGROUND,
                        verification_target=canonical,
                        expected_state_updates={"browser_specifically_requested": canonical},
                    )
                ],
                description=f"Open {app.name}",
            )

        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="open_application",
                    params={"app_name": canonical},
                    description=f"Open {app.name}",
                    verification=VerificationStrategy.WINDOW_FOREGROUND,
                    verification_target=canonical,
                    expected_state_updates={"last_target": canonical},
                )
            ],
            description=f"Open {app.name}",
        )

    # ------------------------------------------------------------------
    def _plan_close_application(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        app = intent.application
        canonical = app.canonical if app else "unknown"
        name = app.name if app else intent.raw_text
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="close_application",
                    params={"app_name": canonical},
                    description=f"Close {name}",
                    verification=VerificationStrategy.NONE,
                )
            ],
            description=f"Close {name}",
        )

    # ------------------------------------------------------------------
    def _plan_browser_navigate(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        steps: list[TaskStep] = []
        dest = intent.destination
        explicit_browser = intent.explicit_browser

        # Resolve browser to use
        browser_to_use = (
            explicit_browser
            or (getattr(state, "browser_specifically_requested", None) if state else None)
            or (getattr(state, "browser_name", None) if state else None)
            or "google_chrome"
        )

        # Step 0: Open/focus browser (if explicitly requested or not running)
        if explicit_browser:
            steps.append(TaskStep(
                step_id="step_0",
                tool="open_browser",
                params={"browser_name": browser_to_use},
                description=f"Open {browser_to_use.replace('_', ' ').title()}",
                verification=VerificationStrategy.BROWSER_FOREGROUND,
                verification_target=browser_to_use,
                skip_if_already="browser_open",
                expected_state_updates={"browser_specifically_requested": browser_to_use},
            ))

        # Priority 0: Homepage navigation
        is_site_home = (
            intent.target_type == "SITE_HOME"
            or (intent.target and intent.target.lower() in ("home", "homepage"))
            or ("homepage" in intent.raw_text.lower() or "home page" in intent.raw_text.lower())
        )
        if is_site_home:
            site = intent.site or (dest.site if dest else None) or (state.web_context.site if state and getattr(state, "web_context", None) else None) or "youtube"
            url = _get_service_url(site) or f"https://www.{site}.com"
            service_name = site.capitalize()
            domain = _get_service_domain(site, url)
            step_idx = len(steps)
            steps.append(TaskStep(
                step_id=f"step_{step_idx}",
                tool="navigate_browser",
                params={
                    "url": url,
                    "service_name": service_name,
                    "browser_name": browser_to_use,
                    "verify_domain": domain,
                },
                description=f"Navigate to {service_name} homepage",
                verification=VerificationStrategy.URL_TITLE_POLL if domain else VerificationStrategy.NONE,
                verification_target=domain,
                requires_previous=bool(explicit_browser),
                expected_state_updates={
                    "active_page_url": url,
                    "web_context.site": site,
                    "web_context.page": "home",
                },
            ))
            return TaskPlan(
                intent=intent,
                steps=steps,
                description=f"Navigate to {service_name} homepage",
            )

        # Resolve URL
        url: str | None = None
        service_name: str | None = None
        domain: str | None = None

        if dest:
            # Handle ordinal/pronoun entity reference
            if intent.entity and intent.entity.ordinal is not None:
                resolved = self._resolver.resolve_ordinal(intent.raw_text, state)
                if resolved and resolved.resolved:
                    url = resolved.value
                    service_name = "Page"
                    domain = None
                else:
                    return TaskPlan(
                        intent=intent,
                        steps=[],
                        description="Navigate to entity",
                        requires_resolution=True,
                        resolution_error=resolved.reason if resolved else "no context for ordinal",
                    )

            elif dest.is_search and dest.search_query:
                url = _build_search_url(dest.site or dest.raw, dest.search_query)
                service_name = dest.raw.capitalize()
                domain = _get_service_domain(dest.site or dest.raw, url)

            elif dest.url:
                url = dest.url
                service_name = dest.raw.capitalize()
                domain = _get_service_domain(dest.site or dest.raw, url)

            elif dest.site or dest.raw:
                svc = dest.site or dest.raw
                url = _get_service_url(svc) or f"https://{svc}"
                service_name = dest.raw.capitalize()
                domain = _get_service_domain(svc, url)

        # Pronoun/reference resolution
        elif intent.entity and intent.entity.reference:
            resolved = self._resolver.resolve_pronoun(intent.raw_text, state)
            if resolved and resolved.resolved:
                url = resolved.value
                service_name = "Page"
            else:
                return TaskPlan(
                    intent=intent,
                    steps=[],
                    description="Navigate",
                    requires_resolution=True,
                    resolution_error=resolved.reason if resolved else "no context for pronoun",
                )

        if not url:
            return TaskPlan(
                intent=intent,
                steps=steps,
                description="Navigate browser",
                requires_resolution=True,
                resolution_error="could not determine navigation URL",
            )

        step_idx = len(steps)
        steps.append(TaskStep(
            step_id=f"step_{step_idx}",
            tool="navigate_browser",
            params={
                "url": url,
                "service_name": service_name,
                "browser_name": browser_to_use,
                "verify_domain": domain,
            },
            description=f"Navigate to {service_name or url}",
            verification=(
                VerificationStrategy.URL_TITLE_POLL if domain
                else VerificationStrategy.NONE
            ),
            verification_target=domain,
            requires_previous=bool(explicit_browser),
            expected_state_updates=(
                {
                    "active_page_url": url,
                    "web_context.site": "youtube" if ((url and "youtube.com" in url) or (dest and dest.site == "youtube")) else (dest.site if dest else None),
                    "web_context.channel": (intent.entity.name if intent.entity else None) or intent.target or (dest.raw if dest else None),
                    "web_context.page": "channel",
                }
                if ((intent.entity and intent.entity.kind == "channel") or intent.target_type == "CHANNEL" or (url and "/@" in url))
                else {
                    "active_page_url": url,
                    "web_context.site": (dest.site if dest else None),
                }
            ),
        ))

        return TaskPlan(
            intent=intent,
            steps=steps,
            description=f"Navigate to {service_name or url}",
        )

    # ------------------------------------------------------------------
    def _plan_browser_search(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        steps: list[TaskStep] = []
        dest = intent.destination
        explicit_browser = intent.explicit_browser

        browser_to_use = (
            explicit_browser
            or (getattr(state, "browser_specifically_requested", None) if state else None)
            or (getattr(state, "browser_name", None) if state else None)
            or "google_chrome"
        )

        # Step 0: Open browser if explicitly requested
        if explicit_browser:
            steps.append(TaskStep(
                step_id="step_0",
                tool="open_browser",
                params={"browser_name": browser_to_use},
                description=f"Open {browser_to_use.replace('_', ' ').title()}",
                verification=VerificationStrategy.BROWSER_FOREGROUND,
                verification_target=browser_to_use,
                skip_if_already="browser_open",
                expected_state_updates={"browser_specifically_requested": browser_to_use},
            ))

        query = (dest.search_query if dest else None) or intent.raw_text
        service = (dest.site if dest else None) or (intent.search_domain) or "google"
        url = _build_search_url(service, query)
        domain = _get_service_domain(service, url)

        step_idx = len(steps)
        steps.append(TaskStep(
            step_id=f"step_{step_idx}",
            tool="search_browser",
            params={
                "query": query,
                "service": service,
                "url": url,
                "browser_name": browser_to_use,
                "verify_domain": domain,
            },
            description=f"Search {service.capitalize()} for '{query}'",
            verification=VerificationStrategy.URL_TITLE_POLL,
            verification_target=domain,
            requires_previous=bool(explicit_browser),
            expected_state_updates={
                "active_page_url": url,
                "web_context.site": service,
            },
        ))

        return TaskPlan(
            intent=intent,
            steps=steps,
            description=f"Search {service.capitalize()} for '{query}'",
        )

    # ------------------------------------------------------------------
    def _plan_messaging_send(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Plan a WhatsApp message send — always requires user confirmation."""
        entity = intent.entity
        recipient = entity.name if entity else "unknown"

        # Extract message text from raw text if not in entity
        msg_text = ""
        import re as _re
        m = _re.search(
            r"(?:saying|with|the\s+message)\s+['\"]?(.+?)['\"]?\s*$",
            intent.raw_text,
            _re.IGNORECASE,
        )
        if m:
            msg_text = m.group(1).strip()

        steps: list[TaskStep] = []

        # Step 0: Open WhatsApp
        steps.append(TaskStep(
            step_id="step_0",
            tool="open_application",
            params={"app_name": "whatsapp"},
            description="Open WhatsApp",
            verification=VerificationStrategy.WINDOW_FOREGROUND,
            verification_target="whatsapp",
            skip_if_already="whatsapp_open",
        ))

        # Step 1: Prepare message — requires confirmation (high-risk)
        steps.append(TaskStep(
            step_id="step_1",
            tool="prepare_message",
            params={
                "recipient": recipient,
                "message_text": msg_text,
                "app_name": "whatsapp",
            },
            description=f"Prepare message to {recipient}",
            verification=VerificationStrategy.CONFIRMATION_REQUIRED,
            is_high_risk=True,
            requires_previous=True,
        ))

        return TaskPlan(
            intent=intent,
            steps=steps,
            description=f"Send WhatsApp message to {recipient}",
            has_high_risk_steps=True,
        )

    # ------------------------------------------------------------------
    def _plan_screen_read(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="take_screenshot",
                    params={},
                    description="Take screenshot",
                    verification=VerificationStrategy.NONE,
                )
            ],
            description="Take screenshot",
        )

    # ------------------------------------------------------------------
    def _plan_file_operation(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        entity = intent.entity
        if getattr(intent, "count_only", False) or "how many" in intent.raw_text.lower():
            target = (
                intent.target
                or (entity.name if entity else None)
                or (state.current_directory if state and getattr(state, "current_directory", None) else None)
                or "desktop"
            )
            parent = intent.parent
            raw_lower = intent.raw_text.lower()
            if "folder" in raw_lower or (entity and entity.kind == "folder"):
                item_type = "folder"
            elif "file" in raw_lower or (entity and entity.kind == "file"):
                item_type = "file"
            else:
                item_type = "all"
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="count_directory_items",
                        params={"target": target, "parent": parent, "item_type": item_type},
                        description=f"Count {item_type}s in {target}",
                        verification=VerificationStrategy.NONE,
                    )
                ],
                description=f"Count {item_type}s in {target}",
            )

        if intent.intent_type.upper() == "SEARCH_FILES":
            target_dir = intent.target or (entity.name if entity else None) or "desktop"
            query = intent.query or intent.raw_text
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="search_files",
                        params={"directory": target_dir, "query": query},
                        description=f"Search for {query} in {target_dir}",
                        verification=VerificationStrategy.FILESYSTEM_DIRECTORY,
                        verification_target=target_dir,
                    )
                ],
                description=f"Search files for {query}",
            )

        if intent.intent_type.upper() == "LIST_FILES":
            target_dir = (entity.name if entity else None) or "desktop"
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="list_files",
                        params={"directory": target_dir},
                        description=f"List files in {target_dir}",
                        verification=VerificationStrategy.NONE,
                        expected_state_updates={"current_directory": target_dir},
                    )
                ],
                description=f"List files in {target_dir}",
            )

        if entity and entity.ordinal is not None:
            # Check if this ordinal is for video or web context
            wc = getattr(state, "web_context", None) if state else None
            is_in_youtube = bool(wc and getattr(wc, "site", None) == "youtube")
            has_web_list = bool(wc and getattr(wc, "current_list", None))
            if entity.kind == "video" or is_in_youtube or has_web_list:
                return self._plan_select_item(intent, state)

            resolved = self._resolver.resolve_ordinal(intent.raw_text, state)
            is_resolved_video = (
                resolved
                and (
                    resolved.kind == "video"
                    or resolved.type == "video"
                    or (
                        resolved.value
                        and resolved.value.startswith(("http://", "https://"))
                    )
                )
            )
            if is_resolved_video:
                return self._plan_select_item(intent, state)

            path = resolved.value if resolved and resolved.resolved else None
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="open_file",
                        params={"path": path, "index": entity.ordinal, "use_last_result": True},
                        description=(
                            f"Open file: {path}" if path
                            else f"Open item {entity.ordinal + 1}"
                        ),
                        verification=VerificationStrategy.WINDOW_FOREGROUND,
                    )
                ],
                description=f"Open item {entity.ordinal + 1}",
            )

        # List files / open file explorer
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="open_application",
                    params={"app_name": "file_explorer"},
                    description="Open File Explorer",
                    verification=VerificationStrategy.WINDOW_FOREGROUND,
                    verification_target="file_explorer",
                )
            ],
            description="Open File Explorer",
        )

    # ------------------------------------------------------------------
    def _plan_select_item(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Plan selecting or opening an item from an active list.

        Supports web video, file, or search result.
        """
        entity = intent.entity
        resolved = self._resolver.resolve_ordinal(intent.raw_text, state)
        if not resolved or not resolved.resolved:
            err_msg = (
                resolved.reason if resolved
                else "No context found to resolve item reference"
            )
            return TaskPlan(
                intent=intent,
                steps=[],
                description="Select item",
                requires_resolution=True,
                resolution_error=err_msg,
            )

        wc = getattr(state, "web_context", None) if state else None
        is_explicit_fs = resolved.kind in ("folder", "file") or resolved.type in ("folder", "file")
        is_youtube = not is_explicit_fs and bool(
            resolved.kind == "video"
            or resolved.type == "video"
            or (wc and getattr(wc, "site", None) == "youtube")
            or (resolved.value and "youtube.com" in resolved.value)
        )

        # Web video selection
        if is_youtube or (resolved.value and resolved.value.startswith(("http://", "https://"))):
            browser_to_use = (
                intent.explicit_browser
                or (getattr(state, "browser_specifically_requested", None) if state else None)
                or (getattr(state, "browser_name", None) if state else None)
                or "google_chrome"
            )
            item_title = (resolved.metadata or {}).get("title") or resolved.value
            url = resolved.value
            if not url or not url.startswith(("http://", "https://")):
                url = f"https://www.youtube.com/results?search_query={quote_plus(str(item_title))}"

            domain = _get_service_domain("youtube", url) or "youtube.com"
            ordinal_num = (entity.ordinal + 1) if entity and entity.ordinal is not None else 1

            step = TaskStep(
                step_id="step_0",
                tool="navigate_browser",
                params={
                    "url": url,
                    "service_name": "YouTube",
                    "browser_name": browser_to_use,
                    "verify_domain": domain,
                },
                description=f"Open video #{ordinal_num}: {item_title}",
                verification=(
                    VerificationStrategy.URL_TITLE_POLL if domain
                    else VerificationStrategy.NONE
                ),
                verification_target=domain,
                expected_state_updates={
                    "active_page_url": url,
                    "web_context.video": item_title,
                    "web_context.video_url": url,
                    "web_context.page": "video",
                    "web_context.ordinal_index": (entity.ordinal if entity else None),
                },
            )
            return TaskPlan(
                intent=intent,
                steps=[step],
                description=f"Open video #{ordinal_num}: {item_title}",
            )

        # Filesystem file or folder selection
        path = resolved.value
        idx = entity.ordinal if entity and entity.ordinal is not None else 0
        is_folder = (
            resolved.kind == "folder"
            or resolved.type == "folder"
            or (resolved.metadata or {}).get("type") == "folder"
            or (resolved.metadata or {}).get("is_dir")
        )
        if is_folder:
            folder_name = path or (resolved.metadata or {}).get("name") or f"item_{idx + 1}"
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="open_folder",
                        params={"folder": folder_name, "folder_name": folder_name, "path": path},
                        description=f"Open folder: {folder_name}",
                        verification=VerificationStrategy.FILESYSTEM_DIRECTORY,
                        verification_target=folder_name,
                        expected_state_updates={"current_directory": path or folder_name},
                    )
                ],
                description=f"Open folder: {folder_name}",
            )

        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="open_file",
                    params={"path": path, "index": idx, "use_last_result": True},
                    description=f"Open file: {path}" if path else f"Open item {idx + 1}",
                    verification=VerificationStrategy.WINDOW_FOREGROUND,
                )
            ],
            description=f"Open file: {path}" if path else f"Open item {idx + 1}",
        )

    # ------------------------------------------------------------------
    def _plan_open_content(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Plan opening structured content like a course or playlist."""
        dest = intent.destination
        browser_to_use = (
            intent.explicit_browser
            or (getattr(state, "browser_specifically_requested", None) if state else None)
            or (getattr(state, "browser_name", None) if state else None)
            or "google_chrome"
        )
        c_name = (intent.entity.name if intent.entity else None) or intent.raw_text
        url = (dest.url if dest else None) or f"https://www.youtube.com/results?search_query={quote_plus(c_name)}"

        step = TaskStep(
            step_id="step_0",
            tool="navigate_browser",
            params={
                "url": url,
                "service_name": "YouTube",
                "browser_name": browser_to_use,
                "verify_domain": "youtube.com",
            },
            description=f"Open {c_name}",
            verification=VerificationStrategy.URL_TITLE_POLL,
            verification_target="youtube.com",
            expected_state_updates={
                "active_page_url": url,
                "web_context.course": c_name,
                "web_context.playlist": c_name,
                "web_context.page": "course",
            },
        )
        return TaskPlan(
            intent=intent,
            steps=[step],
            description=f"Open {c_name}",
        )

    # ------------------------------------------------------------------
    def _plan_scroll(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Plan scrolling the active application or browser page."""
        direction = (intent.entity.name if intent.entity else None) or "down"
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="scroll_page",
                    params={"direction": direction},
                    description=f"Scroll {direction}",
                    verification=VerificationStrategy.NONE,
                )
            ],
            description=f"Scroll {direction}",
        )

    # ------------------------------------------------------------------
    def _plan_click(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Plan clicking a UI element."""
        target = (intent.entity.name if intent.entity else None) or intent.raw_text
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="click_element",
                    params={"target": target},
                    description=f"Click {target}",
                    verification=VerificationStrategy.NONE,
                )
            ],
            description=f"Click {target}",
        )

    # ------------------------------------------------------------------
    def _plan_open_folder(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        raw_target = (intent.entity.name if intent.entity and intent.entity.name else intent.target) or "desktop"
        target = raw_target.lower()
        parent = intent.parent
        display_name = raw_target.replace("_", " ").title()
        return TaskPlan(
            intent=intent,
            steps=[
                TaskStep(
                    step_id="step_0",
                    tool="open_folder",
                    params={"target": target, "parent": parent, "display_name": display_name},
                    description=f"Open {display_name}",
                    verification=VerificationStrategy.FILESYSTEM_DIRECTORY,
                    verification_target=target,
                    expected_state_updates={
                        "current_directory": target,
                        "active_application": "File Explorer",
                    },
                )
            ],
            description=f"Open {display_name}",
        )

    # ------------------------------------------------------------------
    def _plan_multi_step(
        self,
        intent: ComputerIntent,
        state: Any | None,
    ) -> TaskPlan:
        """Decompose a MULTI_STEP intent's ``actions`` list into typed TaskSteps."""
        steps: list[TaskStep] = []

        for i, action_str in enumerate(intent.actions):
            # Format: "open_browser:edge", "navigate:youtube", "search:youtube:LangGraph"
            parts = action_str.split(":", 2)
            action_key = parts[0].lower()
            param1 = parts[1] if len(parts) > 1 else ""
            param2 = parts[2] if len(parts) > 2 else ""

            if action_key == "open_browser":
                canonical = param1 or intent.explicit_browser or "google_chrome"
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="open_browser",
                    params={"browser_name": canonical},
                    description=f"Open {canonical.replace('_', ' ').title()}",
                    verification=VerificationStrategy.BROWSER_FOREGROUND,
                    verification_target=canonical,
                    skip_if_already="browser_open",
                    expected_state_updates={"browser_specifically_requested": canonical},
                ))

            elif action_key == "navigate":
                svc = param1.strip()
                url = _get_service_url(svc) or f"https://{svc}"
                domain = _get_service_domain(svc, url)
                browser = intent.explicit_browser or "google_chrome"
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="navigate_browser",
                    params={"url": url, "service_name": svc.capitalize(),
                            "browser_name": browser, "verify_domain": domain},
                    description=f"Navigate to {svc.capitalize()}",
                    verification=VerificationStrategy.URL_TITLE_POLL,
                    verification_target=domain,
                    requires_previous=(i > 0),
                ))

            elif action_key == "search":
                svc = param1.strip()
                query = param2.strip() or intent.raw_text
                url = _build_search_url(svc, query)
                domain = _get_service_domain(svc, url)
                browser = intent.explicit_browser or "google_chrome"
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="search_browser",
                    params={"query": query, "service": svc, "url": url,
                            "browser_name": browser, "verify_domain": domain},
                    description=f"Search {svc.capitalize()} for '{query}'",
                    verification=VerificationStrategy.URL_TITLE_POLL,
                    verification_target=domain,
                    requires_previous=(i > 0),
                ))

            elif action_key in ("open_app", "open_application"):
                canonical = param1.strip()
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="open_application",
                    params={"app_name": canonical},
                    description=f"Open {canonical.replace('_', ' ').title()}",
                    verification=VerificationStrategy.WINDOW_FOREGROUND,
                    verification_target=canonical,
                ))

            elif action_key == "message":
                recipient = param1.strip()
                msg_text = param2.strip()
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="prepare_message",
                    params={
                        "recipient": recipient,
                        "message_text": msg_text,
                        "app_name": "whatsapp",
                    },
                    description=f"Prepare message to {recipient}",
                    verification=VerificationStrategy.CONFIRMATION_REQUIRED,
                    is_high_risk=True,
                    requires_previous=(i > 0),
                ))

            elif action_key in ("open_folder", "navigate_folder"):
                folder = param1.strip() or "Desktop"
                steps.append(TaskStep(
                    step_id=f"step_{i}",
                    tool="open_folder",
                    params={"target": folder, "folder": folder},
                    description=f"Open {folder} folder",
                    verification=VerificationStrategy.FILESYSTEM_DIRECTORY,
                    verification_target=folder,
                    requires_previous=(i > 0),
                ))

        if not steps:
            # No recognized actions: fallback
            return TaskPlan(
                intent=intent,
                steps=[
                    TaskStep(
                        step_id="step_0",
                        tool="computer_control_fallback",
                        params={"text": intent.raw_text},
                        description=f"Execute: '{intent.raw_text}'",
                        verification=VerificationStrategy.NONE,
                    )
                ],
                description=intent.raw_text,
            )

        return TaskPlan(
            intent=intent,
            steps=steps,
            description=f"Multi-step: {' → '.join(s.description for s in steps)}",
        )


# ---------------------------------------------------------------------------
# Allow TaskPlan to be initialized with has_high_risk_steps as a property
# ---------------------------------------------------------------------------
# Patch: add has_high_risk_steps as computed property
_orig_init = TaskPlan.__init__


def _patched_init(self, *args, **kwargs):
    # Remove non-dataclass kwarg before calling dataclass init
    kwargs.pop("has_high_risk_steps", None)
    _orig_init(self, *args, **kwargs)


TaskPlan.__init__ = _patched_init  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

default_planner = SemanticTaskPlanner()

__all__ = [
    "TaskStep",
    "TaskPlan",
    "SemanticTaskPlanner",
    "VerificationStrategy",
    "default_planner",
]
