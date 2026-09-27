"""Confirmation handlers for high-risk / destructive actions on user desktop."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from jarvis_agent.models import ActionRequest

logger = logging.getLogger(__name__)


class ConfirmationHandler(Protocol):
    """Protocol for local user confirmation of destructive / side-effect actions."""

    async def request_approval(self, request: ActionRequest) -> bool:
        """Prompt the user and return True if approved, False if declined."""
        ...


class CliConfirmationHandler:
    """Prompts the local user on the console with a timeout."""

    def __init__(self, default_timeout_seconds: float = 120.0) -> None:
        self.default_timeout = default_timeout_seconds

    async def request_approval(self, request: ActionRequest) -> bool:
        prompt_text = (
            request.confirmation_prompt
            or f"Action '{request.tool}' requires your confirmation. Allow?"
        )
        print("\n" + "=" * 60)
        print("⚠️  SECURITY CONFIRMATION REQUIRED")
        print(f"Action: {request.tool}")
        print(f"Details: {request.params}")
        print(f"Prompt: {prompt_text}")
        print("=" * 60)

        timeout = request.confirmation_timeout_seconds or self.default_timeout

        loop = asyncio.get_running_loop()
        try:
            # Prompt in separate thread to avoid blocking event loop
            answer = await asyncio.wait_for(
                loop.run_in_executor(None, input, "Approve execution? [y/N]: "),
                timeout=timeout,
            )
            return answer.strip().lower() in ("y", "yes")
        except TimeoutError:
            print("\n⏱️ Confirmation timed out. Action declined for safety.")
            return False
        except Exception as exc:
            logger.warning("Error reading user confirmation: %s", exc)
            return False


class AutoApproveConfirmationHandler:
    """Auto-approves all requests (strictly for automated testing)."""

    async def request_approval(self, request: ActionRequest) -> bool:
        logger.info("AutoApproveConfirmationHandler approving action %s", request.action_id)
        return True


class MockConfirmationHandler:
    """Configurable mock confirmation handler for deterministic tests."""

    def __init__(self, approve: bool = True) -> None:
        self.approve = approve
        self.call_count = 0
        self.last_request: ActionRequest | None = None

    async def request_approval(self, request: ActionRequest) -> bool:
        self.call_count += 1
        self.last_request = request
        return self.approve


__all__ = [
    "AutoApproveConfirmationHandler",
    "CliConfirmationHandler",
    "ConfirmationHandler",
    "MockConfirmationHandler",
]
