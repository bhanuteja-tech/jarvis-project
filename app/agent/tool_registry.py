"""Tool Registry for JARVIS.

Maps strongly-typed Intents to callable handler functions and services.
Decouples intent classification from capability execution.

Domain isolation:
- ``ComputerToolRegistry`` — handlers for OS/browser/filesystem intents.
- ``CareerToolRegistry``   — handlers for career intelligence intents.
- ``DomainBoundRegistry``  — wraps either registry and enforces that only
  tools belonging to the session's domain can be executed.

The ``default_tool_registry`` singleton continues to work as before for
backward compatibility with existing callers that do not pass a session.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.routing.taxonomy import Intent, is_browser_control, is_career_intent, is_computer_control

logger = logging.getLogger(__name__)

# Intent sets per domain (used for registry partitioning)
_COMPUTER_INTENTS: frozenset[Intent] = frozenset(
    i for i in Intent
    if is_computer_control(i) or is_browser_control(i)
)

_CAREER_INTENTS: frozenset[Intent] = frozenset(
    i for i in Intent
    if is_career_intent(i)
)


class ToolRegistry:
    """Central registry of agent tools and capabilities."""

    def __init__(self) -> None:
        self._handlers: dict[Intent, Callable[..., Any]] = {}

    def register(self, intent: Intent, handler: Callable[..., Any]) -> None:
        """Register a handler callable for a specific intent."""
        self._handlers[intent] = handler

    def get(self, intent: Intent) -> Callable[..., Any] | None:
        """Retrieve handler callable for an intent."""
        return self._handlers.get(intent)

    def has(self, intent: Intent) -> bool:
        return intent in self._handlers

    def execute(self, intent: Intent, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool associated with the intent."""
        handler = self.get(intent)
        if not handler:
            raise KeyError(f"No tool registered for intent: {intent}")
        return handler(*args, **kwargs)


class DomainBoundRegistry(ToolRegistry):
    """A ToolRegistry wrapper that enforces domain isolation.

    Wraps an underlying registry (computer or career) and raises
    ``DomainViolation`` when a tool from the wrong domain is invoked.
    """

    def __init__(self, domain: str, underlying: ToolRegistry) -> None:
        super().__init__()
        self._domain = domain
        self._underlying = underlying

    def register(self, intent: Intent, handler: Callable[..., Any]) -> None:
        self._underlying.register(intent, handler)

    def get(self, intent: Intent) -> Callable[..., Any] | None:
        self._assert_intent_allowed(intent)
        return self._underlying.get(intent)

    def has(self, intent: Intent) -> bool:
        return self._underlying.has(intent)

    def execute(self, intent: Intent, *args: Any, **kwargs: Any) -> Any:
        self._assert_intent_allowed(intent)
        return self._underlying.execute(intent, *args, **kwargs)

    def _assert_intent_allowed(self, intent: Intent) -> None:
        """Raise DomainViolation if intent does not belong to this domain."""
        from app.jarvis.sessions import DomainViolation

        if self._domain == "computer" and intent in _CAREER_INTENTS:
            raise DomainViolation("computer", "career", action=str(intent))
        if self._domain == "career" and intent in _COMPUTER_INTENTS:
            raise DomainViolation("career", "computer", action=str(intent))


# ---------------------------------------------------------------------------
# Singleton registries
# ---------------------------------------------------------------------------

# Global singleton tool registry (shared, backward-compat)
default_tool_registry = ToolRegistry()

# Domain-specific registries (used by domain-locked sessions)
computer_tool_registry = ToolRegistry()
career_tool_registry = ToolRegistry()

__all__ = [
    "CareerToolRegistry",
    "ComputerToolRegistry",
    "DomainBoundRegistry",
    "ToolRegistry",
    "career_tool_registry",
    "computer_tool_registry",
    "default_tool_registry",
]

# Aliases for clarity in import sites
ComputerToolRegistry = ToolRegistry
CareerToolRegistry = ToolRegistry
