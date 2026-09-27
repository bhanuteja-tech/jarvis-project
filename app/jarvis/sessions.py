"""In-memory session store (Phase 7 decision: no persistence).

One session holds the conversation history plus the artifacts needed for
multi-turn interaction (the candidate input survives between messages so a
user can say "now tailor job 2" without re-uploading). Sessions are
process-local and intentionally lost on restart.

Domain isolation (Phase critical-fix):
- Sessions have a ``domain`` attribute that is LOCKED at creation time.
- The domain is set by which WebSocket endpoint was used to connect:
  /ws/computer  → domain = "computer"  (immutable for the session lifetime)
  /ws/career    → domain = "career"    (immutable for the session lifetime)
- The ``mode`` attribute is kept for backward compatibility with the
  shared /ws/jarvis endpoint but the domain cannot be changed via messages.
- ``assert_domain(required)`` raises ``DomainViolation`` if the session's
  domain does not match the required domain.  This is the enforcement point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

Domain = Literal["career", "computer"]

_COMPUTER_TOOLS = frozenset(
    [
        "open_application",
        "close_application",
        "focus_application",
        "open_folder",
        "navigate_folder",
        "list_files",
        "search_files",
        "open_file",
        "browser_open",
        "browser_navigate",
        "browser_search",
        "browser_back",
        "browser_forward",
        "browser_new_tab",
        "browser_close_tab",
        "screen_read",
        "screen_analyze",
        "ui_click",
        "ui_type",
        "ui_select",
        "messaging_send",
        "confirm_action",
        "reject_action",
        # plan-level action strings from parse_intent / orchestrator
        "desktop_control",
        "help",
        "end_session",
        "interrupt",
    ]
)

_CAREER_TOOLS = frozenset(
    [
        "run_discovery",
        "select_target",
        "cover_letter",
        "resume_analysis",
        "job_details",
        "career_advice",
        "apply_for_role",
        "resume_upload",
        "job_question",
        "tailor_resume",
        "get_results",
        # plan-level action strings from parse_intent / orchestrator
        "casual_chat",
        "general_question",
        "job_search",
        "help",
        "end_session",
        "interrupt",
    ]
)

# Tools allowed in *both* domains (session lifecycle, safe no-ops)
_SHARED_TOOLS = frozenset(["help", "end_session", "interrupt"])


class DomainViolation(Exception):
    """Raised when a session's domain constraint is violated."""

    def __init__(self, session_domain: str, required_domain: str, action: str = "") -> None:
        self.session_domain = session_domain
        self.required_domain = required_domain
        self.action = action
        detail = f"action={action!r} " if action else ""
        super().__init__(
            f"Domain violation: {detail}session is locked to domain '{session_domain}' "
            f"but '{required_domain}' tools were invoked. "
            f"Navigate to /app/{required_domain} to use this feature."
        )


@dataclass
class Session:
    session_id: str
    created_at: str
    user_id: str = "default"
    #: Immutable domain lock — set once at connection time by the WS endpoint.
    #: This is the enforcement boundary: a computer session can NEVER call
    #: career tools and vice versa.
    domain: Domain = "career"
    messages: list[dict[str, Any]] = field(default_factory=list)
    #: Bounded dialogue memory used by the conversational agent (Phase 12).
    history: list[dict[str, Any]] = field(default_factory=list)
    candidate_input: dict[str, Any] | None = None
    last_state: dict[str, Any] | None = None
    pending_prompt: dict[str, Any] | None = None
    active_browser: bool = False
    browser_context: dict[str, Any] = field(default_factory=dict)
    computer_agent: Any | None = None
    typed_context: Any | None = None

    @property
    def mode(self) -> str:
        """Backward-compat alias for domain (used by older code paths)."""
        return self.domain

    @mode.setter
    def mode(self, value: str) -> None:
        # The shared /ws/jarvis endpoint may try to set session.mode from
        # the message's mode field.  We allow this only when the domain has
        # not been locked to a non-default value (i.e. the session was
        # created from the legacy /ws/jarvis endpoint, not /ws/computer or
        # /ws/career).  Once locked, the setter is a silent no-op so that
        # existing orchestrator code does not break.
        if value in ("career", "computer") and not getattr(self, "_domain_locked", False):
            self.domain = value  # type: ignore[assignment]

    def lock_domain(self) -> None:
        """Mark the domain as immutable.  Called by the dedicated WS endpoints."""
        object.__setattr__(self, "_domain_locked", True)

    def assert_domain(self, required: Domain, *, action: str = "") -> None:
        """Raise DomainViolation if session.domain != required."""
        if self.domain != required:
            raise DomainViolation(self.domain, required, action=action)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Return True if the tool is permitted in this session's domain."""
        if tool_name in _SHARED_TOOLS:
            return True
        if self.domain == "computer":
            return tool_name in _COMPUTER_TOOLS
        # career domain
        return tool_name in _CAREER_TOOLS

    def assert_tool_allowed(self, tool_name: str) -> None:
        """Raise DomainViolation if the tool is not permitted in this domain."""
        if not self.is_tool_allowed(tool_name):
            raise DomainViolation(self.domain, "computer" if self.domain == "career" else "career",
                                  action=tool_name)

    def append_message(self, role: str, text: str) -> None:
        self.messages.append(
            {
                "role": role,
                "text": text,
                "ts": datetime.now(UTC).isoformat(),
            }
        )


@dataclass
class ComputerSession(Session):
    """Session locked to the Computer Control domain.

    Uses ComputerAgent and ComputerToolRegistry exclusively with strict per-session state isolation.
    Delegates state, controllers, tasks, circuit breakers, and vaults to SessionContext.
    """

    domain: Domain = "computer"
    _session_context: Any = field(default=None, repr=False)
    _computer_state: Any = field(default=None, repr=False)
    _task_manager: Any = field(default=None, repr=False)
    _circuit_breaker: Any = field(default=None, repr=False)
    _typed_ctx: Any = field(default=None, repr=False)
    _browser_sess: Any = field(default=None, repr=False)

    @property
    def session_context(self) -> Any:
        if self._session_context is None:
            from app.computer.session_context import create_session_context

            self._session_context = create_session_context(
                user_id=self.user_id,
                session_id=self.session_id,
            )
            if self._computer_state is not None:
                self._session_context.computer_state = self._computer_state
            if self._typed_ctx is not None:
                self._session_context.typed_context = self._typed_ctx
            if self._circuit_breaker is not None:
                self._session_context.circuit_breaker = self._circuit_breaker
            if self._task_manager is not None:
                self._session_context.task_manager = self._task_manager
        return self._session_context

    @session_context.setter
    def session_context(self, val: Any) -> None:
        self._session_context = val

    @property
    def computer_state(self) -> Any:
        return self.session_context.computer_state

    @computer_state.setter
    def computer_state(self, val: Any) -> None:
        self.session_context.computer_state = val

    @property
    def typed_context(self) -> Any:
        return self.session_context.typed_context

    @typed_context.setter
    def typed_context(self, val: Any) -> None:
        self.session_context.typed_context = val

    @property
    def circuit_breaker(self) -> Any:
        return self.session_context.circuit_breaker

    @circuit_breaker.setter
    def circuit_breaker(self, val: Any) -> None:
        self.session_context.circuit_breaker = val

    @property
    def task_manager(self) -> Any:
        return self.session_context.task_manager

    @task_manager.setter
    def task_manager(self, val: Any) -> None:
        self.session_context.task_manager = val

    @property
    def vault(self) -> Any:
        return self.session_context.vault

    @vault.setter
    def vault(self, val: Any) -> None:
        self.session_context.vault = val

    @property
    def browser_session(self) -> Any:
        if self._browser_sess is None:
            from app.desktop.browser_session import BrowserSession

            self._browser_sess = BrowserSession()
        return self._browser_sess

    @browser_session.setter
    def browser_session(self, val: Any) -> None:
        self._browser_sess = val

    @property
    def tool_registry(self) -> Any:
        return self.session_context.tool_registry

    @property
    def agent(self) -> Any:
        return self.session_context.agent

    @property
    def router(self) -> Any:
        return self.session_context.router

    @property
    def planner(self) -> Any:
        return self.session_context.planner

    @property
    def semantic_planner(self) -> Any:
        return self.session_context.semantic_planner

    @property
    def llm_router(self) -> Any:
        return self.session_context.llm_router


@dataclass
class CareerSession(Session):
    """Session locked to the Career Intelligence domain.

    Uses CareerAgent and isolated CareerToolRegistry exclusively.
    """

    domain: Domain = "career"
    _session_context: Any = field(default=None, repr=False)
    _tool_registry: Any = field(default=None, repr=False)
    _agent: Any = field(default=None, repr=False)
    _router: Any = field(default=None, repr=False)
    _planner: Any = field(default=None, repr=False)

    @property
    def session_context(self) -> Any:
        if self._session_context is None:
            from app.computer.session_context import create_session_context

            self._session_context = create_session_context(
                user_id=self.user_id,
                session_id=self.session_id,
            )
        return self._session_context

    @session_context.setter
    def session_context(self, val: Any) -> None:
        self._session_context = val

    @property
    def tool_registry(self) -> Any:
        if self._tool_registry is None:
            from app.agent.tool_registry import DomainBoundRegistry, ToolRegistry

            self._tool_registry = DomainBoundRegistry("career", ToolRegistry())
        return self._tool_registry

    @property
    def agent(self) -> Any:
        if self._agent is None:
            from app.jarvis.career_agent import CareerAgent

            self._agent = CareerAgent()
        return self._agent

    @property
    def router(self) -> Any:
        if self._router is None:
            from app.routing.router import IntentRouter

            self._router = IntentRouter(planner=self.planner)
        return self._router

    @property
    def planner(self) -> Any:
        if self._planner is None:
            from app.routing.planner import ExecutionPlanner

            self._planner = ExecutionPlanner()
        return self._planner


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(
        self,
        session_id: str | None = None,
        *,
        user_id: str = "default",
        domain: Domain = "career",
        lock: bool = False,
    ) -> Session:
        key = session_id or str(uuid4())
        if key not in self._sessions:
            now_iso = datetime.now(UTC).isoformat()
            if domain == "computer":
                sess: Session = ComputerSession(
                    session_id=key, user_id=user_id, created_at=now_iso, domain="computer"
                )
            else:
                sess = CareerSession(
                    session_id=key, user_id=user_id, created_at=now_iso, domain="career"
                )
            if lock:
                sess.lock_domain()
            self._sessions[key] = sess
        return self._sessions[key]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)


global_session_store = InMemorySessionStore()

__all__ = [
    "CareerSession",
    "ComputerSession",
    "Domain",
    "DomainViolation",
    "InMemorySessionStore",
    "Session",
    "global_session_store",
]
