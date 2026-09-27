"""Jarvis Agent Client Package.

Lightweight desktop client connecting to the Jarvis backend over WebSocket to
execute local OS, browser, and filesystem actions on behalf of the user.
"""

from __future__ import annotations

from jarvis_agent.client import JarvisAgentClient
from jarvis_agent.confirmation import (
    AutoApproveConfirmationHandler,
    CliConfirmationHandler,
    ConfirmationHandler,
)
from jarvis_agent.models import ActionRequest, ActionResult

__all__ = [
    "ActionRequest",
    "ActionResult",
    "AutoApproveConfirmationHandler",
    "CliConfirmationHandler",
    "ConfirmationHandler",
    "JarvisAgentClient",
]
