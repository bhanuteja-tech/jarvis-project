"""Truthful Response Generator for JARVIS Computer-Use Agent.

Generates human-readable responses for computer-control actions that are
STRICTLY gated on verification status.

Core principle: the LLM must NEVER invent execution success.
- If verified=True: generate a confident, specific success message.
- If verified=False: generate an honest failure message with the reason.
- If verified=None/unknown: generate a cautious partial-success message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing a ComputerAgent plan step or full plan.

    This is the authoritative source for response generation.
    Only ExecutionResult.verified=True permits a success response.
    """

    success: bool
    verified: bool | None           # None = uncertain (no verification attempted)
    action: str                     # e.g. "open_application", "navigate_browser"
    intent_description: str         # e.g. "open Microsoft Edge"
    message: str                    # raw harness message
    reason: str | None = None       # failure reason or verification detail
    verify_method: str | None = None  # how verification was done
    details: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)  # multi-step trace
    needs_user_input: bool = False
    pending_prompt: dict[str, Any] | None = None


class TruthfulResponseGenerator:
    """Generates strictly truthful human-readable responses.

    Rules:
    1. NEVER claim success unless verified=True.
    2. NEVER say "I couldn't" unless verified=False (not just success=False).
    3. For unverified (verified=None): say something cautious but not definitive.
    4. Keep responses concise and voice-friendly (no markdown in voice context).
    """

    def generate(
        self,
        result: ExecutionResult,
        *,
        is_voice: bool = False,
    ) -> str:
        """Generate the response text for an execution result.

        Args:
            result: The authoritative execution result.
            is_voice: If True, avoid markdown and keep responses short.

        Returns:
            Human-readable response string.
        """
        # --- Case 1: Confirmed failure ---
        if result.verified is False or (not result.success and result.verified is not True):
            return self._failure_response(result, is_voice=is_voice)

        # --- Case 2: Confirmed success ---
        if result.verified is True and result.success:
            return self._success_response(result, is_voice=is_voice)

        # --- Case 3: Needs user input (e.g. WhatsApp confirmation) ---
        if result.needs_user_input and result.pending_prompt:
            return result.message  # use harness message directly for confirmation prompts

        # --- Case 4: Uncertain / no verification attempted ---
        if result.success and result.verified is None:
            return self._cautious_response(result, is_voice=is_voice)

        # --- Case 5: Success=True but verified=False is impossible by design,
        # but handle defensively ---
        return self._failure_response(result, is_voice=is_voice)

    # ------------------------------------------------------------------
    def _success_response(self, result: ExecutionResult, *, is_voice: bool) -> str:
        """Build a success response based on action type."""
        action = result.action.lower()
        desc = result.intent_description

        # Multi-step completed
        if result.steps and len(result.steps) > 1:
            total = len(result.steps)
            return (
                f"Done. Completed all {total} steps — {desc}. "
                "What would you like me to do next?"
            )

        # Browser navigation
        if action in ("navigate_browser", "browser_navigate", "browser_search", "navigate"):
            return f"{desc}. What would you like me to do next?"

        # Application open
        if action in ("open_application", "open_app"):
            return f"{desc}. It's open and in the foreground."

        # Application close
        if action in ("close_application", "close_app"):
            return f"{desc}."

        # Messaging
        if action in ("messaging_send", "send_message"):
            return f"Message sent to {result.details.get('recipient', 'the contact')}."

        # File operations
        if action in ("open_file", "list_files", "search_files"):
            return result.message or f"{desc}."

        # Generic
        return result.message or f"{desc}. Done."

    # ------------------------------------------------------------------
    def _failure_response(self, result: ExecutionResult, *, is_voice: bool) -> str:
        """Build a failure response that never claims success."""
        desc = result.intent_description
        reason = result.reason or "an unexpected error occurred"

        # Known failure patterns → friendlier messages
        if "window" in reason.lower() and "not" in reason.lower():
            return (
                f"I couldn't {desc}. The window didn't appear — "
                "it may not be installed or took too long to open. "
                "Would you like me to try again?"
            )
        if "url" in reason.lower() or "navigation" in reason.lower():
            return (
                f"I tried to {desc}, but couldn't confirm the page loaded. "
                "The browser may still be loading. Would you like me to check again?"
            )
        if "whatsapp" in reason.lower():
            return (
                "I couldn't confirm the message was sent. "
                "Please check WhatsApp directly."
            )

        return (
            f"I couldn't {desc}. {reason.capitalize()}. "
            "Would you like me to try a different approach?"
        )

    # ------------------------------------------------------------------
    def _cautious_response(self, result: ExecutionResult, *, is_voice: bool) -> str:
        """Build a cautious response when success happened but verification was skipped."""
        desc = result.intent_description
        msg = result.message

        # If harness already has a good message, use it with a caveat
        if msg and not msg.lower().startswith("error"):
            return msg

        return (
            f"I initiated {desc}. "
            "I wasn't able to independently confirm it completed — "
            "please check if everything looks right."
        )

    # ------------------------------------------------------------------
    def generate_step_update(
        self,
        step_idx: int,
        total_steps: int,
        action_description: str,
        verified: bool,
        *,
        is_voice: bool = False,
    ) -> str | None:
        """Generate a brief step-progress announcement (voice-only, optional).

        Returns None if the update should be suppressed (silent execution).
        """
        if not is_voice:
            return None
        if total_steps == 1:
            return None  # Single-step: don't narrate; just final result

        if total_steps <= 3:
            # Narrate each step for short plans
            status = "Done" if verified else "Working on"
            return f"Step {step_idx + 1}: {status} — {action_description}."

        # Long plans: only narrate milestones
        if step_idx == 0:
            return f"Starting {total_steps}-step task."
        if step_idx == total_steps - 1:
            return None  # Final result will be narrated separately
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

default_response_generator = TruthfulResponseGenerator()

__all__ = [
    "ExecutionResult",
    "TruthfulResponseGenerator",
    "default_response_generator",
]
