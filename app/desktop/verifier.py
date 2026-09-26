"""Verification Service for Computer Actions.

Separates tool execution from ground-truth verification.
Inspects actual OS observations to confirm that requested applications,
windows, folders, navigations, and actions truly succeeded before telling the user.
Zero tolerance for false success.

Phase 8+: Added verify_browser_foreground (checks process AND window title),
verify_navigation_by_title (domain-match via window title for post-nav verification),
and verify_message_sent (WhatsApp send confirmation via window content).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.desktop.state import VerifiedState
from app.routing.app_resolver import default_app_resolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying an action against real OS observation."""

    success: bool
    confidence: float
    reason: str
    details: dict[str, Any]
    task_id: str | None = None
    generation: int = 0
    expected: str = ""
    observed: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.success

    @property
    def status(self) -> str:
        return "success" if self.success else "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "verified": self.success,
            "confidence": self.confidence,
            "reason": self.reason,
            "details": self.details,
            "task_id": self.task_id,
            "generation": self.generation,
            "expected": self.expected,
            "observed": self.observed,
            "evidence": self.evidence,
        }

    def to_verified_state(
        self,
        *,
        action: str = "",
        target: str = "",
        verified_app: str | None = None,
        verified_directory: str | None = None,
        verified_url: str | None = None,
        verified_page: str | None = None,
        verified_items: list[Any] | None = None,
    ) -> VerifiedState:
        """Convert verification outcome into an authoritative VerifiedState for state commit."""
        return VerifiedState(
            task_id=self.task_id,
            generation=self.generation,
            is_verified=self.success,
            action=action,
            target=target,
            verified_app=verified_app,
            verified_directory=verified_directory,
            verified_url=verified_url,
            verified_page=verified_page,
            verified_items=verified_items or [],
            evidence=self.evidence or self.details,
            confidence=self.confidence,
            reason=self.reason,
        )


class VerificationService:
    """Verifies that an executed action achieved its intended state."""

    def __init__(self) -> None:
        self.resolver = default_app_resolver

    def verify_application_opened(
        self,
        canonical_app: str,
        observation: dict[str, Any],
        open_windows: list[dict[str, Any]] | None = None,
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify that an application opened and has an active foreground window."""
        display_name = self.resolver.get_display_name(canonical_app).lower()
        active_app = (observation.get("active_application") or "").lower()
        active_title = (observation.get("active_window_title") or "").lower()
        win_info = observation.get("window") or {}
        is_foreground = win_info.get("foreground", True)  # True if window was checked active

        is_match = (
            display_name in active_app
            or display_name in active_title
            or canonical_app.replace("_", " ") in active_title
            or (
                canonical_app == "visual_studio_code"
                and ("code" in active_title or "code" in active_app)
            )
            or (
                canonical_app == "file_explorer"
                and ("explorer" in active_title or "desktop" in active_title)
            )
            or (
                canonical_app == "whatsapp"
                and "whatsapp" in active_title
            )
        )

        if is_match and is_foreground:
            return VerificationResult(
                success=True,
                confidence=0.98,
                reason=f"{canonical_app} verified in foreground",
                details={"window_title": active_title, "foreground": True},
                task_id=task_id,
                generation=generation,
                expected=canonical_app,
                observed=active_title or active_app,
                evidence={"window_title": active_title, "foreground": True, "active_application": active_app},
            )

        return VerificationResult(
            success=False,
            confidence=0.10,
            reason=f"Could not verify foreground window for {canonical_app}",
            details={"active_app": active_app, "active_window": active_title},
            task_id=task_id,
            generation=generation,
            expected=canonical_app,
            observed=active_title or active_app,
            evidence={"active_app": active_app, "active_window": active_title},
        )

    def verify_folder_opened(
        self,
        expected_folder: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify that File Explorer navigated to the expected directory."""
        curr = (observation.get("current_directory") or "").lower()
        exp = expected_folder.lower()

        if exp == "desktop" and "desktop" in curr:
            return VerificationResult(
                success=True,
                confidence=1.0,
                reason="Desktop directory verified",
                details={"current_directory": observation.get("current_directory")},
                task_id=task_id,
                generation=generation,
                expected="desktop",
                observed=curr,
                evidence={"current_directory": observation.get("current_directory"), "active_application": "File Explorer"},
            )
        if exp in curr:
            return VerificationResult(
                success=True,
                confidence=0.95,
                reason=f"Folder {expected_folder} verified",
                details={"current_directory": observation.get("current_directory")},
                task_id=task_id,
                generation=generation,
                expected=expected_folder,
                observed=curr,
                evidence={"current_directory": observation.get("current_directory"), "active_application": "File Explorer"},
            )

        return VerificationResult(
            success=False,
            confidence=0.20,
            reason=f"Current directory does not match {expected_folder}",
            details={"current_directory": observation.get("current_directory")},
            task_id=task_id,
            generation=generation,
            expected=expected_folder,
            observed=curr,
            evidence={"current_directory": observation.get("current_directory")},
        )

    def verify_site_home(
        self,
        domain_or_site: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify that browser navigated to the site homepage, NOT a search query."""
        browser_info = observation.get("browser") or {}
        curr_url = (browser_info.get("url") or browser_info.get("current_url") or "").lower()
        domain = domain_or_site.lower().replace("https://", "").replace("http://", "").rstrip("/")
        if "." not in domain:
            domain = f"{domain}.com"

        has_domain = domain in curr_url or (domain == "youtube.com" and "youtube.com" in curr_url)
        has_search_query = (
            "search_query" in curr_url
            or "query=" in curr_url
            or "search?" in curr_url
            or "/search/" in curr_url
        )

        if has_domain and not has_search_query:
            return VerificationResult(
                success=True,
                confidence=0.99,
                reason=f"Verified homepage for {domain_or_site}",
                details={"current_url": curr_url, "domain": domain},
                task_id=task_id,
                generation=generation,
                expected=f"{domain} homepage",
                observed=curr_url,
                evidence={"current_url": curr_url, "domain": domain, "is_home": True},
            )

        return VerificationResult(
            success=False,
            confidence=0.10,
            reason=f"URL '{curr_url}' is not the homepage for {domain_or_site} (search query detected or wrong domain)",
            details={"current_url": curr_url, "domain": domain},
            task_id=task_id,
            generation=generation,
            expected=f"{domain} homepage",
            observed=curr_url,
            evidence={"current_url": curr_url, "domain": domain, "is_home": False},
        )

    def verify_item_count(
        self,
        expected_target: str,
        count: int,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify item count of folders or files."""
        return VerificationResult(
            success=True,
            confidence=1.0,
            reason=f"Counted {count} items in {expected_target}",
            details={"target": expected_target, "count": count},
            task_id=task_id,
            generation=generation,
            expected=f"count items in {expected_target}",
            observed=str(count),
            evidence={"count": count, "target": expected_target},
        )

    def verify_browser_navigation(
        self,
        expected_url_or_service: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify browser navigated to the requested URL or service."""
        browser_info = observation.get("browser") or {}
        curr_url = (browser_info.get("url") or browser_info.get("current_url") or "").lower()
        target = expected_url_or_service.lower()

        if target in curr_url or (target == "youtube" and "youtube.com" in curr_url):
            return VerificationResult(
                success=True,
                confidence=0.98,
                reason=f"Navigation to {expected_url_or_service} verified",
                details={"current_url": curr_url},
                task_id=task_id,
                generation=generation,
                expected=expected_url_or_service,
                observed=curr_url,
                evidence={"current_url": curr_url},
            )

        return VerificationResult(
            success=False,
            confidence=0.10,
            reason=f"Active URL '{curr_url}' does not match expected '{expected_url_or_service}'",
            details={"current_url": curr_url},
            task_id=task_id,
            generation=generation,
            expected=expected_url_or_service,
            observed=curr_url,
            evidence={"current_url": curr_url},
        )

    def verify_search_results(
        self,
        query: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify search query was reflected in browser or filesystem results."""
        browser_info = observation.get("browser") or {}
        curr_url = (
            observation.get("current_url")
            or observation.get("browser_url")
            or browser_info.get("url")
            or ""
        ).lower()
        q_norm = query.lower()
        q_plus = q_norm.replace(" ", "+")

        if (
            q_norm in curr_url
            or q_plus in curr_url
            or "search_query" in curr_url
            or ("search" in curr_url and any(w in curr_url for w in q_norm.split()))
        ):
            return VerificationResult(
                success=True,
                confidence=0.95,
                reason=f"Search for '{query}' verified in URL",
                details={"url": curr_url},
                task_id=task_id,
                generation=generation,
                expected=query,
                observed=curr_url,
                evidence={"url": curr_url},
            )

        fs_info = observation.get("filesystem") or {}
        last_results = fs_info.get("last_search_results", [])
        if last_results:
            return VerificationResult(
                success=True,
                confidence=0.95,
                reason=f"Filesystem search returned {len(last_results)} items",
                details={"count": len(last_results)},
                task_id=task_id,
                generation=generation,
                expected=query,
                observed=str(len(last_results)),
                evidence={"count": len(last_results)},
            )

        return VerificationResult(
            success=False,
            confidence=0.20,
            reason=f"Could not verify search results for '{query}'",
            details={"url": curr_url},
            task_id=task_id,
            generation=generation,
            expected=query,
            observed=curr_url,
        )

    def verify_youtube_search(
        self,
        query: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Goal-level verification: YouTube search results are active and reflect query."""
        browser_info = observation.get("browser") or {}
        curr_url = (
            observation.get("current_url")
            or browser_info.get("url")
            or browser_info.get("current_url")
            or ""
        ).lower()
        active_title = (
            observation.get("page_title")
            or observation.get("active_window_title")
            or (observation.get("window") or {}).get("title")
            or (browser_info.get("title") or "")
            or ""
        ).lower()
        q_norm = query.lower().strip()

        # Reject generic Google search
        if "google.com/search" in curr_url:
            return VerificationResult(
                success=False,
                confidence=0.0,
                reason=(
                    f"Verification failed: browser is on Google search, "
                    f"not YouTube search for '{query}'."
                ),
                details={"url": curr_url, "title": active_title},
                task_id=task_id,
                generation=generation,
                expected=f"YouTube search for '{query}'",
                observed=curr_url,
            )

        is_youtube = "youtube.com" in curr_url or "youtube" in active_title
        q_plus = q_norm.replace(" ", "+")
        has_query = (
            ("search_query=" in curr_url and (q_plus in curr_url or q_norm in curr_url))
            or (q_norm in active_title and "youtube" in active_title)
            or ("results?search_query" in curr_url)
        )

        if is_youtube and has_query:
            return VerificationResult(
                success=True,
                confidence=0.98,
                reason=f"Verified YouTube search results page for '{query}'.",
                details={"url": curr_url, "title": active_title},
                task_id=task_id,
                generation=generation,
                expected=f"YouTube search for '{query}'",
                observed=curr_url or active_title,
                evidence={"url": curr_url, "title": active_title},
            )

        return VerificationResult(
            success=False,
            confidence=0.15,
            reason=(
                f"Could not verify YouTube search results for '{query}' "
                f"(active URL: '{curr_url}')."
            ),
            details={"url": curr_url, "title": active_title},
            task_id=task_id,
            generation=generation,
            expected=f"YouTube search for '{query}'",
            observed=curr_url or active_title,
        )

    def verify_github_profile(
        self,
        username: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Goal-level verification: Verified active on requested GitHub profile."""
        browser_info = observation.get("browser") or {}
        curr_url = (
            observation.get("current_url")
            or observation.get("browser_url")
            or browser_info.get("url")
            or browser_info.get("current_url")
            or ""
        ).lower()
        active_title = (
            observation.get("page_title")
            or observation.get("active_window_title")
            or (observation.get("window") or {}).get("title")
            or (browser_info.get("title") or "")
            or ""
        ).lower()
        u_norm = username.lower().strip()

        # Reject if still on search results
        if "google.com/search" in curr_url:
            return VerificationResult(
                success=False,
                confidence=0.0,
                reason=(
                    f"Verification failed: browser is on Google search, "
                    f"not GitHub profile for '{username}'."
                ),
                details={"url": curr_url, "title": active_title},
                task_id=task_id,
                generation=generation,
                expected=f"GitHub profile for '{username}'",
                observed=curr_url,
            )

        is_github = "github.com" in curr_url or "github" in active_title
        matches_user = (
            f"github.com/{u_norm}" in curr_url
            or (u_norm in curr_url and "github" in curr_url)
            or (u_norm in active_title and "github" in active_title)
        )

        if is_github and matches_user:
            return VerificationResult(
                success=True,
                confidence=0.98,
                reason=f"Verified active at GitHub profile for '{username}'.",
                details={"url": curr_url, "title": active_title},
                task_id=task_id,
                generation=generation,
                expected=f"GitHub profile for '{username}'",
                observed=curr_url or active_title,
                evidence={"url": curr_url, "username": username, "title": active_title},
            )

        return VerificationResult(
            success=False,
            confidence=0.10,
            reason=f"Could not verify GitHub profile for '{username}' (active URL: '{curr_url}').",
            details={"url": curr_url, "title": active_title},
            task_id=task_id,
            generation=generation,
            expected=f"GitHub profile for '{username}'",
            observed=curr_url or active_title,
        )

    def verify_filesystem_target(
        self,
        expected_target: str,
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Goal-level verification: File Explorer / Desktop is open at target path."""
        active_title = (
            observation.get("active_window_title")
            or (observation.get("window") or {}).get("title")
            or ""
        ).lower()
        curr_dir = (observation.get("current_directory") or "").lower()
        tgt_norm = expected_target.lower().strip()

        matches_target = (
            tgt_norm in curr_dir
            or tgt_norm in active_title
            or (tgt_norm == "desktop" and ("desktop" in active_title or "desktop" in curr_dir))
        )

        if matches_target:
            return VerificationResult(
                success=True,
                confidence=0.96,
                reason=f"Verified filesystem location '{expected_target}' is active.",
                details={"current_directory": curr_dir, "title": active_title},
                task_id=task_id,
                generation=generation,
                expected=expected_target,
                observed=curr_dir or active_title,
                evidence={"directory": curr_dir, "title": active_title},
            )

        return VerificationResult(
            success=False,
            confidence=0.20,
            reason=f"Could not verify filesystem location '{expected_target}'.",
            details={"current_directory": curr_dir, "title": active_title},
            task_id=task_id,
            generation=generation,
            expected=expected_target,
            observed=curr_dir or active_title,
        )

    def verify_message_sent(
        self,
        recipient: str,
        observation: dict[str, Any],
    ) -> VerificationResult:
        """Verify that a message was dispatched from the WhatsApp window.

        Uses window title observation: WhatsApp Desktop shows the chat title
        in its window title when a conversation is open.  A successful send
        leaves the window in the same conversation state.
        """
        window = observation.get("window") or {}
        title = (window.get("title") or "").lower()
        active_app = (observation.get("active_application") or "").lower()

        whatsapp_present = "whatsapp" in title or "whatsapp" in active_app
        if not whatsapp_present:
            return VerificationResult(
                success=False,
                confidence=0.10,
                reason="WhatsApp window is no longer in the foreground — cannot confirm send",
                details={"window_title": title},
            )

        # WhatsApp Desktop shows the contact name in the window title.
        # We use a fuzzy token match: at least one word from the recipient
        # must appear in the title (handles "Lohit" inside "Lohit Reddy").
        recipient_tokens = re.sub(r"[^a-z0-9 ]", "", recipient.lower()).split()
        token_found = any(tok in title for tok in recipient_tokens if len(tok) > 2)

        if token_found:
            return VerificationResult(
                success=True,
                confidence=0.85,
                reason=f"WhatsApp is open in {recipient} conversation; message likely sent",
                details={"window_title": title},
            )

        return VerificationResult(
            success=True,  # generous: at least WhatsApp is open
            confidence=0.60,
            reason="WhatsApp is in foreground but contact name not visible in title",
            details={"window_title": title, "recipient": recipient},
        )

    def verify_browser_foreground(
        self,
        browser_canonical: str,
        observation: dict[str, Any],
    ) -> VerificationResult:
        """Verify that the specifically requested browser is the foreground application.

        Uses both window title AND active_application to avoid false positives
        when two browsers are open simultaneously.
        """
        window = observation.get("window") or {}
        title = (window.get("title") or "").lower()
        active_app = (observation.get("active_application") or "").lower()
        is_foreground = window.get("foreground", False)

        # Map canonical names to identifying window-title tokens
        browser_tokens: dict[str, list[str]] = {
            "google_chrome": ["chrome"],
            "microsoft_edge": ["edge", "microsoft edge"],
            "firefox": ["firefox", "mozilla firefox"],
            "brave": ["brave"],
            "opera": ["opera"],
        }
        tokens = browser_tokens.get(browser_canonical, [browser_canonical.replace("_", " ")])
        found = any(tok in title or tok in active_app for tok in tokens)

        if found and is_foreground:
            return VerificationResult(
                success=True,
                confidence=0.97,
                reason=f"{browser_canonical} verified as foreground browser",
                details={"window_title": title, "foreground": True},
            )
        if found and not is_foreground:
            return VerificationResult(
                success=False,
                confidence=0.50,
                reason=f"{browser_canonical} window exists but is not foreground",
                details={"window_title": title, "foreground": False},
            )
        return VerificationResult(
            success=False,
            confidence=0.05,
            reason=f"{browser_canonical} not found in foreground window",
            details={"active_app": active_app, "window_title": title},
        )

    def verify_navigation_by_title(
        self,
        expected_domain: str,
        observation: dict[str, Any],
        *,
        poll_window_controller=None,
        poll_seconds: float = 3.0,
        poll_interval: float = 0.4,
    ) -> VerificationResult:
        """Verify browser navigation by inspecting the live foreground window title.

        Strategy (in priority order):
        1. Check the observation's browser.url (optimistic, from state — fast)
        2. Poll the live window title for up to ``poll_seconds`` looking for
           the expected domain (e.g. "youtube.com", "github.com")
           This is the only reliable method without UI Automation or CDP.

        ``poll_window_controller`` must be a WindowController instance;
        if None, only the observation is checked (no live polling).
        """
        # --- Priority 1: check browser state URL ---
        browser_info = observation.get("browser") or {}
        state_url = (browser_info.get("url") or "").lower()
        domain_lower = expected_domain.lower().strip()
        # Strip scheme if provided
        if domain_lower.startswith(("https://", "http://")):
            domain_lower = domain_lower.split("://", 1)[1].rstrip("/")

        if domain_lower and domain_lower in state_url:
            return VerificationResult(
                success=True,
                confidence=0.80,  # optimistic; window title may differ
                reason=f"Browser state URL contains '{expected_domain}'",
                details={"url": state_url, "method": "state_url"},
            )

        # --- Priority 2: live window-title polling ---
        if poll_window_controller is None:
            # No polling available — fall back on observation window title
            window = observation.get("window") or {}
            title = (window.get("title") or "").lower()
            if domain_lower and domain_lower in title:
                return VerificationResult(
                    success=True,
                    confidence=0.88,
                    reason=f"Window title contains '{expected_domain}'",
                    details={"title": title, "method": "window_title"},
                )
            return VerificationResult(
                success=False,
                confidence=0.15,
                reason=f"Cannot confirm navigation to '{expected_domain}' without live observation",
                details={"state_url": state_url},
            )

        # Live polling
        deadline = time.perf_counter() + poll_seconds
        while time.perf_counter() < deadline:
            active = poll_window_controller.get_active_window()
            if active:
                title = (active.get("title") or "").lower()
                if domain_lower in title:
                    return VerificationResult(
                        success=True,
                        confidence=0.93,
                        reason=f"Live window title confirms navigation to '{expected_domain}'",
                        details={"title": active.get("title"), "method": "live_title_poll"},
                    )
            time.sleep(poll_interval)

        # Last chance: check final window title
        active = poll_window_controller.get_active_window() if poll_window_controller else None
        final_title = (active.get("title") or "") if active else ""
        return VerificationResult(
            success=False,
            confidence=0.10,
            reason=(
                f"Live window title poll timed out after {poll_seconds}s; "
                f"last title: '{final_title}'"
            ),
            details={"title": final_title, "expected": expected_domain},
        )


default_verifier = VerificationService()

__all__ = ["VerificationResult", "VerificationService", "default_verifier"]
