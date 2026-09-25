"""Mandatory Domain Isolation Tests — Tests 1–8.

Verifies that the six enforcement layers correctly prevent cross-domain tool
execution:
  1. Frontend route  (verified by test_computer_ws_has_computer_domain,
                      test_career_ws_has_career_domain)
  2. WebSocket endpoint (/ws/computer vs /ws/career — tested below)
  3. Session domain lock (Session.lock_domain() — unit tests)
  4. Orchestrator assert_tool_allowed (orchestrator-level guard — unit tests)
  5. Tool registry DomainBoundRegistry (unit tests)
  6. Tool execution (deferred to future integration tests)

Tests are deterministic and require no network / OS access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.jarvis.sessions import (
    DomainViolation,
    InMemorySessionStore,
    Session,
)


def _client() -> TestClient:
    from app.main import create_app
    from tests.support import make_settings

    return TestClient(create_app(make_settings()))


# ---------------------------------------------------------------------------
# Unit tests: Session domain locking
# ---------------------------------------------------------------------------

class TestSessionDomainLocking:
    """Test 1: Session created from /ws/computer has domain='computer' locked."""

    def test_session_defaults_to_career(self) -> None:
        store = InMemorySessionStore()
        s = store.get_or_create()
        assert s.domain == "career"

    def test_computer_session_locked(self) -> None:
        """Session created with domain='computer' and lock=True cannot be changed."""
        store = InMemorySessionStore()
        s = store.get_or_create(domain="computer", lock=True)
        assert s.domain == "computer"
        # Attempt to change via mode setter (legacy path) — must be silently ignored
        s.mode = "career"
        assert s.domain == "computer", "Domain must not change after lock_domain()"

    def test_career_session_locked(self) -> None:
        """Session created with domain='career' and lock=True cannot be changed."""
        store = InMemorySessionStore()
        s = store.get_or_create(domain="career", lock=True)
        assert s.domain == "career"
        s.mode = "computer"
        assert s.domain == "career", "Domain must not change after lock_domain()"

    def test_unlocked_session_can_change_mode(self) -> None:
        """Legacy /ws/jarvis sessions (unlocked) can change mode."""
        store = InMemorySessionStore()
        s = store.get_or_create()
        assert s.domain == "career"
        s.mode = "computer"
        assert s.domain == "computer"

    def test_assert_domain_passes_when_correct(self) -> None:
        s = Session(session_id="x", created_at="now", domain="computer")
        s.assert_domain("computer")  # must not raise

    def test_assert_domain_raises_when_wrong(self) -> None:
        s = Session(session_id="x", created_at="now", domain="computer")
        with pytest.raises(DomainViolation) as exc_info:
            s.assert_domain("career")
        assert exc_info.value.session_domain == "computer"
        assert exc_info.value.required_domain == "career"


# ---------------------------------------------------------------------------
# Unit tests: Tool allowlist enforcement
# ---------------------------------------------------------------------------

class TestToolAllowlist:
    """Test 2: Computer session rejects career tools and vice versa."""

    def test_computer_session_allows_computer_tools(self) -> None:
        s = Session(session_id="x", created_at="now", domain="computer")
        computer_tools = [
            "desktop_control",
            "open_application",
            "browser_navigate",
            "open_folder",
            "list_files",
            "messaging_send",
        ]
        for tool in computer_tools:
            assert s.is_tool_allowed(tool), f"Computer tool '{tool}' should be allowed"

    def test_computer_session_rejects_career_tools(self) -> None:
        """Test 3: Computer session must reject all career tools."""
        s = Session(session_id="x", created_at="now", domain="computer")
        career_tools = [
            "run_discovery",
            "select_target",
            "cover_letter",
            "resume_analysis",
            "job_details",
            "career_advice",
            "apply_for_role",
            "resume_upload",
        ]
        for tool in career_tools:
            assert not s.is_tool_allowed(tool), (
                f"Career tool '{tool}' must NOT be allowed in computer session"
            )

    def test_career_session_allows_career_tools(self) -> None:
        s = Session(session_id="x", created_at="now", domain="career")
        career_tools = [
            "run_discovery",
            "select_target",
            "cover_letter",
            "resume_analysis",
            "job_details",
        ]
        for tool in career_tools:
            assert s.is_tool_allowed(tool), f"Career tool '{tool}' should be allowed"

    def test_career_session_rejects_computer_tools(self) -> None:
        """Test 4: Career session must reject all computer tools."""
        s = Session(session_id="x", created_at="now", domain="career")
        computer_tools = [
            "open_application",
            "browser_navigate",
            "list_files",
            "messaging_send",
        ]
        for tool in computer_tools:
            assert not s.is_tool_allowed(tool), (
                f"Computer tool '{tool}' must NOT be allowed in career session"
            )

    def test_shared_tools_allowed_in_both(self) -> None:
        """Test 5: Shared tools (end_session, interrupt, help) work in both domains."""
        for domain in ("computer", "career"):
            s = Session(session_id="x", created_at="now", domain=domain)  # type: ignore[arg-type]
            for tool in ("end_session", "interrupt", "help"):
                assert s.is_tool_allowed(tool), (
                    f"Shared tool '{tool}' must be allowed in domain '{domain}'"
                )

    def test_assert_tool_raises_for_wrong_domain(self) -> None:
        """Test 6: assert_tool_allowed raises DomainViolation for wrong domain."""
        s = Session(session_id="x", created_at="now", domain="computer")
        with pytest.raises(DomainViolation) as exc_info:
            s.assert_tool_allowed("run_discovery")
        assert exc_info.value.action == "run_discovery"
        assert exc_info.value.session_domain == "computer"


# ---------------------------------------------------------------------------
# Integration tests: DomainBoundRegistry
# ---------------------------------------------------------------------------

class TestDomainBoundRegistry:
    """Test 7: DomainBoundRegistry enforces tool access at the registry layer."""

    def test_computer_registry_blocks_career_intents(self) -> None:
        from app.agent.tool_registry import DomainBoundRegistry, ToolRegistry
        from app.routing.taxonomy import Intent

        underlying = ToolRegistry()
        registry = DomainBoundRegistry("computer", underlying)

        with pytest.raises(DomainViolation):
            registry.get(Intent.CAREER_JOB_SEARCH)

    def test_career_registry_blocks_computer_intents(self) -> None:
        from app.agent.tool_registry import DomainBoundRegistry, ToolRegistry
        from app.routing.taxonomy import Intent

        underlying = ToolRegistry()
        registry = DomainBoundRegistry("career", underlying)

        with pytest.raises(DomainViolation):
            registry.get(Intent.OPEN_APPLICATION)


# ---------------------------------------------------------------------------
# WebSocket endpoint tests: /ws/computer vs /ws/career
# ---------------------------------------------------------------------------

class TestWebSocketDomainEndpoints:
    """Test 8: /ws/computer and /ws/career endpoints exist and are reachable."""

    def test_ws_computer_endpoint_exists(self) -> None:
        """Verify /ws/computer connects successfully."""
        with _client() as tc:
            with tc.websocket_connect("/ws/computer?session_id=test-computer-1") as ws:
                # Connection succeeded — endpoint exists.
                assert ws is not None

    def test_ws_career_endpoint_exists(self) -> None:
        """Verify /ws/career connects successfully."""
        with _client() as tc:
            with tc.websocket_connect("/ws/career?session_id=test-career-1") as ws:
                assert ws is not None

    def test_ws_computer_session_has_computer_domain(self) -> None:
        """Session created via /ws/computer is locked to domain='computer'."""
        from app.api.routes.jarvis import reset_stores_for_tests
        from app.jarvis.sessions import global_session_store

        reset_stores_for_tests()
        sid = "isolation-test-computer"

        with _client() as tc:
            with tc.websocket_connect(f"/ws/computer?session_id={sid}") as _ws:
                pass

        session = global_session_store.get(sid)
        assert session is not None, "Session must be stored"
        assert session.domain == "computer", (
            f"Expected domain='computer', got '{session.domain}'"
        )

    def test_ws_career_session_has_career_domain(self) -> None:
        """Session created via /ws/career is locked to domain='career'."""
        from app.api.routes.jarvis import reset_stores_for_tests
        from app.jarvis.sessions import global_session_store

        reset_stores_for_tests()
        sid = "isolation-test-career"

        with _client() as tc:
            with tc.websocket_connect(f"/ws/career?session_id={sid}") as _ws:
                pass

        session = global_session_store.get(sid)
        assert session is not None, "Session must be stored"
        assert session.domain == "career", (
            f"Expected domain='career', got '{session.domain}'"
        )

    def test_career_session_mode_setter_cannot_unlock(self) -> None:
        """Locked career session cannot be unlocked by sending mode='computer'."""
        from app.api.routes.jarvis import reset_stores_for_tests
        from app.jarvis.sessions import global_session_store

        reset_stores_for_tests()
        sid = "isolation-test-lock-check"

        with _client() as tc:
            with tc.websocket_connect(f"/ws/career?session_id={sid}") as _ws:
                pass

        session = global_session_store.get(sid)
        assert session is not None
        # Simulate what the orchestrator does when it receives mode="computer"
        session.mode = "computer"
        assert session.domain == "career", (
            "Locked session must ignore mode setter"
        )
