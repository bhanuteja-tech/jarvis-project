"""Local desktop client implementation for jarvis_agent."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from jarvis_agent.confirmation import CliConfirmationHandler, ConfirmationHandler
from jarvis_agent.models import ActionRequest, ActionResult

logger = logging.getLogger(__name__)


def get_or_create_device_id(storage_path: Path | None = None) -> str:
    """Retrieve existing persistent device ID or generate and store a new one.

    Ensures each physical machine / agent installation has a stable, unique
    device identifier across reconnects.
    """
    if storage_path is None:
        home = Path.home()
        storage_dir = home / ".jarvis"
        storage_path = storage_dir / "device_id"
    else:
        storage_dir = storage_path.parent

    try:
        if storage_path.exists():
            content = storage_path.read_text(encoding="utf-8").strip()
            if content:
                return content
    except Exception as exc:
        logger.warning("Could not read persistent device_id from %s: %s", storage_path, exc)

    new_id = f"dev_{uuid.uuid4().hex[:16]}"
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(new_id, encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist device_id to %s: %s", storage_path, exc)

    return new_id


class JarvisAgentClient:
    """Lightweight local agent client connecting to Jarvis server over WebSocket."""

    def __init__(
        self,
        server_ws_url: str,
        session_id: str,
        access_token: str,
        *,
        device_id: str | None = None,
        refresh_token: str | None = None,
        auth_base_url: str | None = None,
        confirmation_handler: ConfirmationHandler | None = None,
        local_harness: Any | None = None,
    ) -> None:
        self.server_ws_url = server_ws_url
        self.session_id = session_id
        self.access_token = access_token
        self.device_id = device_id or get_or_create_device_id()
        self.refresh_token = refresh_token
        self.auth_base_url = auth_base_url or self._derive_http_base_url(server_ws_url)
        self.confirmation_handler: ConfirmationHandler = (
            confirmation_handler or CliConfirmationHandler()
        )
        self.local_harness = local_harness
        self._running = False
        self._ws: Any = None

    def _derive_http_base_url(self, ws_url: str) -> str:
        """Derive base HTTP API URL from WebSocket URL."""
        clean = ws_url.replace("ws://", "http://").replace("wss://", "https://")
        parts = clean.split("/ws/")
        return parts[0] if parts else clean

    async def refresh_access_token(self) -> bool:
        """Refresh JWT access token using refresh_token if available."""
        if not self.refresh_token:
            logger.debug("No refresh token available; skipping proactive refresh.")
            return False

        refresh_endpoint = f"{self.auth_base_url.rstrip('/')}/api/auth/refresh"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    refresh_endpoint,
                    json={"refresh_token": self.refresh_token},
                )
                if res.status_code == 200:
                    data = res.json()
                    self.access_token = data.get("access_token", self.access_token)
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    logger.info("Successfully refreshed access token.")
                    return True
                logger.warning(
                    "Token refresh failed with status %d: %s",
                    res.status_code,
                    res.text,
                )
                return False
        except Exception as exc:
            logger.warning("Token refresh request failed: %s", exc)
            return False

    async def execute_action_request(self, request: ActionRequest) -> ActionResult:
        """Process an inbound ActionRequest, checking confirmation and running locally."""
        # 1. Threaded confirmation check
        if request.requires_confirmation:
            logger.info("Action %s requires local user confirmation.", request.action_id)
            approved = await self.confirmation_handler.request_approval(request)
            if not approved:
                logger.warning("User declined action %s (%s)", request.action_id, request.tool)
                prompt_desc = request.confirmation_prompt or request.tool
                return ActionResult(
                    action_id=request.action_id,
                    step_id=request.step_id,
                    success=False,
                    cancelled=True,
                    message=f"Action declined by user: {prompt_desc}",
                )

        # 2. Local tool execution with execution timeout
        try:
            return await asyncio.wait_for(
                self._run_tool(request),
                timeout=request.timeout_seconds,
            )
        except TimeoutError:
            logger.error("Action %s execution timed out locally.", request.action_id)
            return ActionResult(
                action_id=request.action_id,
                step_id=request.step_id,
                success=False,
                message=f"Action execution timed out after {request.timeout_seconds}s",
            )
        except Exception as exc:
            logger.exception("Error executing action %s locally: %s", request.action_id, exc)
            return ActionResult(
                action_id=request.action_id,
                step_id=request.step_id,
                success=False,
                message=f"Local execution error: {exc}",
            )

    async def _run_tool(self, request: ActionRequest) -> ActionResult:
        """Run the requested tool via the local harness or fallback implementation."""
        if self.local_harness is not None:
            # Run in worker thread if synchronous
            res = await asyncio.to_thread(
                self.local_harness.execute_command, request.tool, request.params
            )
            return ActionResult(
                action_id=request.action_id,
                step_id=request.step_id,
                success=res.success,
                message=res.message,
                details=res.details,
                observation={"last_action": request.tool, "success": res.success},
            )

        # Fallback simulator if no harness provided
        logger.info(
            "Executing simulated tool %s with params %s",
            request.tool,
            request.params,
        )
        return ActionResult(
            action_id=request.action_id,
            step_id=request.step_id,
            success=True,
            message=f"Executed {request.tool} successfully",
            details=request.params,
            observation={"executed_tool": request.tool, "status": "ok"},
        )

    def build_ws_url(self) -> str:
        """Construct authenticated WebSocket URL with query parameters."""
        sep = "&" if "?" in self.server_ws_url else "?"
        return (
            f"{self.server_ws_url}{sep}"
            f"session_id={self.session_id}&"
            f"client_type=agent&"
            f"device_id={self.device_id}&"
            f"token={self.access_token}"
        )

    async def dispatch_inbound_message(
        self, raw_message: str | dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse inbound message and handle action_request if present."""
        if isinstance(raw_message, str):
            try:
                msg = json.loads(raw_message)
            except Exception:
                return None
        else:
            msg = raw_message

        msg_type = msg.get("type")
        if msg_type == "action_request":
            request = ActionRequest.from_dict(msg)
            result = await self.execute_action_request(request)
            return result.to_dict()

        return None


__all__ = ["JarvisAgentClient", "get_or_create_device_id"]
