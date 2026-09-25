"""Career Intelligence Agent for JARVIS.

Central execution agent for Career Intelligence workflows (Phases 1-6 & 12).
Strictly isolated from Computer Control.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CareerAgent:
    """Agent executing Career Intelligence workflows.

    Enforces that computer-control tools cannot be executed here.
    """

    def __init__(self, orchestrator: Any | None = None) -> None:
        self._orchestrator = orchestrator

    async def run(
        self,
        text: str,
        *,
        session: Any | None = None,
        is_voice: bool = False,
    ) -> Any:
        """Run career pipeline or conversational assistant."""
        if session is not None:
            from app.jarvis.sessions import DomainViolation
            if getattr(session, "domain", None) != "career":
                raise DomainViolation(
                    session_domain=getattr(session, "domain", "unknown"),
                    required_domain="career",
                    action="career_agent_run",
                )

        logger.info("CareerAgent executing career workflow for text=%r", text[:60])
        # Career workflows execute through JarvisOrchestrator pipeline
        return None


default_career_agent = CareerAgent()

__all__ = ["CareerAgent", "default_career_agent"]
