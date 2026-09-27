"""Remote Agent Dispatcher for Step 4.

Dispatches computer actions to the user's remote desktop agent via WebSocket
with strict session namespacing, confirmation timeouts, and safety gating.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.config.settings import Settings, get_settings
from app.jarvis.events import (
    ActionRequestPayload,
    ActionResultPayload,
    EventType,
    make_event,
)

if TYPE_CHECKING:
    from app.computer.session_context import SessionContext

logger = logging.getLogger(__name__)


class NoRemoteAgentConnectedError(RuntimeError):
    """Raised when remote action execution is required but no jarvis_agent is connected."""


class ActionTimeoutError(TimeoutError):
    """Raised when a remote action fails to return within its timeout budget."""


class ActionCancelledError(RuntimeError):
    """Raised when an action is declined or cancelled by the user."""


class RemoteAgentDispatcher:
    """Dispatches computer actions to remote desktop agents or local fallback."""

    def __init__(
        self,
        session_context: SessionContext,
        settings: Settings | None = None,
    ) -> None:
        self.session_context = session_context
        self.settings = settings or get_settings()
        self._seq = 0

    @property
    def is_agent_connected(self) -> bool:
        """Check whether a remote jarvis_agent WebSocket is currently connected."""
        ws = self.session_context.agent_ws
        if ws is None:
            return False
        # If client state has closed flag, detect it
        client_state = getattr(ws, "client_state", None)
        if client_state is not None and getattr(client_state, "name", "") == "DISCONNECTED":
            return False
        return not getattr(ws, "closed", False)

    async def dispatch_action(
        self,
        step_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        requires_confirmation: bool = False,
        confirmation_prompt: str | None = None,
        timeout_seconds: float | None = None,
        confirmation_timeout_seconds: float | None = None,
    ) -> ActionResultPayload:
        """Dispatch an action to the remote agent or fail safe if no agent is connected."""
        effective_timeout = timeout_seconds or self.settings.jarvis_remote_action_timeout_seconds
        effective_confirm_timeout = (
            confirmation_timeout_seconds or self.settings.jarvis_confirmation_timeout_seconds
        )

        # 1. Gate remote vs local fallback
        if not self.is_agent_connected:
            if not self.settings.jarvis_allow_local_execution_fallback:
                logger.warning(
                    "Remote action dispatch blocked: no agent connected for session '%s' "
                    "and jarvis_allow_local_execution_fallback is False.",
                    self.session_context.session_id,
                )
                raise NoRemoteAgentConnectedError(
                    f"No local agent connected for session '{self.session_context.session_id}'. "
                    f"Direct server-side execution is prohibited by policy."
                )

            # Allowed ONLY for local development
            logger.info(
                "No remote agent connected for session '%s'; executing locally via "
                "jarvis_allow_local_execution_fallback opt-in.",
                self.session_context.session_id,
            )
            return await self._execute_locally(step_id, tool, params)

        # 2. Prepare remote action request
        action_id = f"act_{uuid4().hex[:12]}"
        fut: asyncio.Future[ActionResultPayload] = asyncio.get_running_loop().create_future()

        # Authoritative session-bound storage
        self.session_context.pending_actions[action_id] = fut

        payload = ActionRequestPayload(
            action_id=action_id,
            session_id=self.session_context.session_id,
            step_id=step_id,
            tool=tool,
            params=params,
            requires_confirmation=requires_confirmation,
            confirmation_prompt=confirmation_prompt,
            timeout_seconds=effective_timeout,
            confirmation_timeout_seconds=effective_confirm_timeout,
        )

        self._seq += 1
        envelope = make_event(
            EventType.ACTION_REQUEST,
            seq=self._seq,
            **payload.to_dict(),
        )

        try:
            ws = self.session_context.agent_ws
            if ws is None:
                raise NoRemoteAgentConnectedError("Agent WebSocket disconnected before dispatch.")
            await ws.send_json(envelope)

            # Separate timeout budget: confirmation wait (if applicable) + execution timeout
            total_wait = effective_timeout + 5.0
            if requires_confirmation:
                total_wait += effective_confirm_timeout

            result = await asyncio.wait_for(fut, timeout=total_wait)
            if result.cancelled:
                raise ActionCancelledError(result.message or "Action was cancelled by user.")
            return result
        except TimeoutError as exc:
            logger.error(
                "Action '%s' (step=%s, tool=%s) timed out after %0.1fs",
                action_id,
                step_id,
                tool,
                total_wait,
            )
            raise ActionTimeoutError(
                f"Action '{action_id}' (tool={tool}) timed out after {total_wait:.1f}s"
            ) from exc
        finally:
            self.session_context.pending_actions.pop(action_id, None)

    async def _execute_locally(
        self,
        step_id: str,
        tool: str,
        params: dict[str, Any],
    ) -> ActionResultPayload:
        """Execute action via local AgentHarness for standalone developer mode."""
        harness = self.session_context.agent_harness
        if harness is None:
            return ActionResultPayload(
                action_id=f"act_local_{step_id}",
                step_id=step_id,
                success=False,
                message="Local agent harness is not configured.",
            )

        res = harness.execute_command(tool, params)
        return ActionResultPayload(
            action_id=f"act_local_{step_id}",
            step_id=step_id,
            success=res.success,
            message=res.message,
            details=res.details,
            observation={"last_action": tool, "success": res.success},
        )


__all__ = [
    "ActionCancelledError",
    "ActionTimeoutError",
    "NoRemoteAgentConnectedError",
    "RemoteAgentDispatcher",
]
