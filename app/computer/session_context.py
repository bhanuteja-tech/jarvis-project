"""SessionContext: isolated execution context for a multi-tenant computer session.

ARCHITECTURAL NOTE: PHYSICAL CONTROL VS DATA ISOLATION
SessionContext isolates Python memory, state, task generations, circuit
breakers, and encrypted credential vaults across concurrent sessions.
However, concurrent REAL OS automation safety is UNVERIFIED until Step 4
(local client agent extraction) ships. In a single-machine backend process,
controllers invoking Win32 APIs (HWNDs, process launching, foreground focus)
target the single physical desktop of that machine. Step 4 resolves this by
forwarding action envelopes to remote local agents on each user's computer.

REDIS PERSISTENCE SPLIT (Step 3B specification):
- PERSISTED (to Redis / DB):
    * Conversation history and metadata (session_id, user_id, timestamps)
    * ComputerState logical fields (current_url, active_application name,
      active_window_id, current_directory, task list, last_action, verification)
    * TypedContext entities (domain state e.g. current YouTube playlist/video)
- RECONSTRUCTED FRESH on reconnect:
    * BrowserManager, BrowserSessionManager (CDP connections, subprocess handles)
    * WindowController (HWNDs, which are dead on process restart)
    * AppController, FileSystemController, DesktopController
    * UIAutomationService, ScreenObserver, VisionController
    * TaskManager (fresh generation, empty background queue)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.agent.task_manager import TaskManager
from app.agent.tool_registry import ToolRegistry
from app.computer.circuit_breaker import ActionCircuitBreaker
from app.computer.context import TypedContext
from app.desktop.app_controller import ApplicationController
from app.desktop.browser_manager import BrowserManager
from app.desktop.browser_session_manager import BrowserSessionManager
from app.desktop.desktop_controller import DesktopController
from app.desktop.filesystem_controller import FileSystemController
from app.desktop.messaging_controller import MessagingController
from app.desktop.screen_observer import ScreenObserver
from app.desktop.state import ComputerState
from app.desktop.ui_automation import UIAutomationService
from app.desktop.vault import (
    BaseCredentialVault,
    EncryptedMemoryCredentialVault,
    PostgresCredentialVault,
)
from app.desktop.vision_controller import VisionController
from app.desktop.window_controller import WindowController

if TYPE_CHECKING:
    from app.computer.agent import ComputerAgent
    from app.computer.semantic_planner import SemanticTaskPlanner
    from app.desktop.agent_harness import AgentHarness
    from app.llm.main_router import MainLLMRouter
    from app.routing.planner import ExecutionPlanner
    from app.routing.router import IntentRouter

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Per-session container providing total data, memory, and credential isolation."""

    user_id: str
    session_id: str = field(default_factory=lambda: str(uuid4()))

    # Logical in-memory and persisted state
    computer_state: ComputerState = field(default_factory=ComputerState)
    typed_context: TypedContext = field(default_factory=TypedContext)
    circuit_breaker: ActionCircuitBreaker = field(default_factory=ActionCircuitBreaker)
    task_manager: TaskManager = field(default_factory=TaskManager)

    # Scoped credential vault (wired in __post_init__, never constructed unscoped)
    vault: BaseCredentialVault | None = field(default=None)

    # Database connection dependencies (optional, for PostgresCredentialVault)
    db_session: Any | None = field(default=None, repr=False)
    session_factory: Any | None = field(default=None, repr=False)
    encryption_key: Any | None = field(default=None, repr=False)

    # Physical OS controllers (reconstructed fresh on reconnect)
    window_controller: WindowController | None = None
    app_controller: ApplicationController | None = None
    filesystem_controller: FileSystemController | None = None
    desktop_controller: DesktopController | None = None
    screen_observer: ScreenObserver | None = None
    ui_automation: UIAutomationService | None = None
    vision_controller: VisionController | None = None
    messaging_controller: MessagingController | None = None
    browser_manager: BrowserManager | None = None
    browser_session_manager: BrowserSessionManager | None = None
    tool_registry: ToolRegistry | None = None
    planner: ExecutionPlanner | None = None
    semantic_planner: SemanticTaskPlanner | None = None
    router: IntentRouter | None = None
    llm_router: MainLLMRouter | None = None
    agent_harness: AgentHarness | None = None
    agent: ComputerAgent | None = None

    # Step 4: Remote Agent WebSocket connection & authoritative pending action registry
    agent_ws: Any | None = field(default=None, repr=False)
    agent_device_id: str | None = field(default=None)
    pending_actions: dict[str, asyncio.Future[Any]] = field(default_factory=dict, repr=False)
    disconnect_timer: asyncio.Task[Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        clean_user = (self.user_id or "").strip()
        if not clean_user:
            raise ValueError(
                "SessionContext requires a non-empty user_id for multi-tenant isolation."
            )
        self.user_id = clean_user

        # 1. Wire Vault strictly scoped to user_id
        if self.vault is None:
            if self.db_session is not None or self.session_factory is not None:
                self.vault = PostgresCredentialVault(
                    user_id=self.user_id,
                    db_session=self.db_session,
                    session_factory=self.session_factory,
                    encryption_key=self.encryption_key,
                )
            else:
                self.vault = EncryptedMemoryCredentialVault(
                    user_id=self.user_id,
                    encryption_key=self.encryption_key,
                )

        # 2. Wire controllers fresh, attaching them to this session's state and vault
        if self.window_controller is None:
            self.window_controller = WindowController()

        if self.app_controller is None:
            self.app_controller = ApplicationController(
                window_controller=self.window_controller,
                state=self.computer_state,
            )

        if self.filesystem_controller is None:
            self.filesystem_controller = FileSystemController(
                window_controller=self.window_controller,
                state=self.computer_state,
            )

        if self.desktop_controller is None:
            self.desktop_controller = DesktopController(
                window_controller=self.window_controller,
                state=self.computer_state,
            )

        if self.screen_observer is None:
            self.screen_observer = ScreenObserver(
                window_controller=self.window_controller,
            )

        if self.ui_automation is None:
            self.ui_automation = UIAutomationService()

        if self.vision_controller is None:
            self.vision_controller = VisionController(
                screen_observer=self.screen_observer,
                window_controller=self.window_controller,
            )

        if self.messaging_controller is None:
            self.messaging_controller = MessagingController(
                app_controller=self.app_controller,
                window_controller=self.window_controller,
                ui_automation=self.ui_automation,
                state=self.computer_state,
            )

        if self.browser_manager is None:
            self.browser_manager = BrowserManager(
                window_controller=self.window_controller,
                state=self.computer_state,
            )

        if self.browser_session_manager is None:
            self.browser_session_manager = BrowserSessionManager(
                window_controller=self.window_controller,
                state=self.computer_state,
            )

        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()

        if self.planner is None:
            from app.routing.planner import ExecutionPlanner

            self.planner = ExecutionPlanner()

        if self.semantic_planner is None:
            from app.computer.semantic_planner import SemanticTaskPlanner

            self.semantic_planner = SemanticTaskPlanner()

        if self.router is None:
            from app.routing.router import IntentRouter

            self.router = IntentRouter(planner=self.planner)

        if self.llm_router is None:
            from app.llm.main_router import MainLLMRouter

            self.llm_router = MainLLMRouter()

        if self.agent_harness is None:
            from app.desktop.agent_harness import AgentHarness

            self.agent_harness = AgentHarness(
                vault=self.vault,
                app_controller=self.app_controller,
                desktop_controller=self.desktop_controller,
                fs_controller=self.filesystem_controller,
                window_controller=self.window_controller,
                screen_observer=self.screen_observer,
                vision_controller=self.vision_controller,
                messaging_controller=self.messaging_controller,
                state=self.computer_state,
                tool_registry=self.tool_registry,
            )

        if self.agent is None:
            from app.computer.agent import ComputerAgent

            self.agent = ComputerAgent(
                state=self.computer_state,
                typed_context=self.typed_context,
                circuit_breaker=self.circuit_breaker,
                harness=self.agent_harness,
                llm_router=self.llm_router,
                task_manager=self.task_manager,
            )

    def get_persisted_state(self) -> dict[str, Any]:
        """Extract logical state fields for Redis/database persistence."""
        typed_dict = (
            self.typed_context.to_dict() if hasattr(self.typed_context, "to_dict") else {}
        )
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "computer_state": self.computer_state.to_dict(),
            "typed_context": typed_dict,
        }

    def restore_logical_state(self, persisted_data: dict[str, Any]) -> None:
        """Restore logical state fields from Redis/database persistence."""
        if not persisted_data:
            return
        c_state = persisted_data.get("computer_state")
        if isinstance(c_state, dict):
            self.computer_state.update(**c_state)
        t_ctx = persisted_data.get("typed_context")
        if isinstance(t_ctx, dict):
            from app.computer.context import TypedContext

            self.typed_context = TypedContext.from_dict(t_ctx)


def create_session_context(
    user_id: str,
    session_id: str | None = None,
    *,
    db_session: Any | None = None,
    session_factory: Any | None = None,
    encryption_key: Any | None = None,
    restored_logical_state: dict[str, Any] | None = None,
) -> SessionContext:
    """Factory creating an isolated SessionContext."""
    ctx = SessionContext(
        user_id=user_id,
        session_id=session_id or str(uuid4()),
        db_session=db_session,
        session_factory=session_factory,
        encryption_key=encryption_key,
    )
    if restored_logical_state:
        ctx.restore_logical_state(restored_logical_state)
    return ctx


__all__ = ["SessionContext", "create_session_context"]
