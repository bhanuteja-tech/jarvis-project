"""Multi-tenant Session Concurrency & Data Isolation Tests.

CRITICAL ARCHITECTURAL DISCLAIMER:
CONCURRENT REAL OS AUTOMATION SAFETY IS UNVERIFIED UNTIL STEP 4 SHIPS.
These tests verify strict isolation of Python in-memory objects:
- ComputerState fields (current_url, active_application, filesystem cwd)
- User-scoped credential vaults and encryption keys
- TaskManager generation increments and task tracking
- ActionCircuitBreaker trip counters and rate limits
- TypedContext domain entities

These tests DO NOT assert that two concurrent sessions can safely automate
a single physical machine's desktop at the same time. On a single backend
instance, Win32 API calls (HWND focus, OS subprocesses, input simulation)
experience physical resource contention until Step 4 (the local-agent split)
extracts OS automation to individual client devices.
"""

import asyncio
from typing import Any

import pytest

from app.computer.session_context import create_session_context
from app.config.settings import get_settings
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import CareerSession, ComputerSession, InMemorySessionStore


class TestSessionConcurrencyIsolation:
    """Validates complete data, memory, and credential isolation across sessions."""

    def test_concurrent_computer_state_isolation(self) -> None:
        """User A and User B maintain completely distinct computer states."""
        ctx_a = create_session_context(user_id="user_alice", session_id="session_a")
        ctx_b = create_session_context(user_id="user_bob", session_id="session_b")

        # Mutate User A's state
        ctx_a.computer_state.update(
            current_url="https://youtube.com/watch?v=123",
            active_application="google_chrome",
            active_window_id="win_1001",
            current_directory="/home/alice/projects",
        )

        # Mutate User B's state
        ctx_b.computer_state.update(
            current_url="https://github.com/my-repo",
            active_application="visual_studio_code",
            active_window_id="win_2002",
            current_directory="/home/bob/downloads",
        )

        # Assert no cross-contamination
        assert ctx_a.computer_state.current_url == "https://youtube.com/watch?v=123"
        assert ctx_a.computer_state.active_application == "google_chrome"
        assert ctx_a.computer_state.active_window_id == "win_1001"
        assert ctx_a.computer_state.current_directory == "/home/alice/projects"

        assert ctx_b.computer_state.current_url == "https://github.com/my-repo"
        assert ctx_b.computer_state.active_application == "visual_studio_code"
        assert ctx_b.computer_state.active_window_id == "win_2002"
        assert ctx_b.computer_state.current_directory == "/home/bob/downloads"

    def test_concurrent_vault_isolation(self) -> None:
        """User A and User B cannot access each other's credentials."""
        ctx_a = create_session_context(user_id="user_alice")
        ctx_b = create_session_context(user_id="user_bob")

        assert ctx_a.vault is not None
        assert ctx_b.vault is not None

        ctx_a.vault.set("github", {"token": "ghp_alice_secret", "username": "alice"})
        ctx_b.vault.set("github", {"token": "ghp_bob_secret", "username": "bob"})

        assert ctx_a.vault.get_field("github", "token") == "ghp_alice_secret"
        assert ctx_b.vault.get_field("github", "token") == "ghp_bob_secret"

        # Deleting in A does not affect B
        assert ctx_a.vault.delete("github") is True
        assert ctx_a.vault.has("github") is False
        assert ctx_b.vault.has("github") is True
        assert ctx_b.vault.get_field("github", "token") == "ghp_bob_secret"

    def test_concurrent_task_manager_generations(self) -> None:
        """TaskManager generations and invalidations are isolated per session."""
        ctx_a = create_session_context(user_id="user_alice")
        ctx_b = create_session_context(user_id="user_bob")

        gen_a = ctx_a.task_manager.current_generation
        gen_b = ctx_b.task_manager.current_generation

        assert gen_a == 1
        assert gen_b == 1

        # Invalidate generation in A and advance
        ctx_a.task_manager.invalidate_generation(gen_a)
        ctx_a.task_manager.next_generation()

        assert not ctx_a.task_manager.is_generation_valid(gen_a)
        assert ctx_a.task_manager.current_generation == 2

        # Session B generation must still be valid and at 1
        assert ctx_b.task_manager.is_generation_valid(gen_b)
        assert ctx_b.task_manager.current_generation == 1

    def test_concurrent_circuit_breaker_isolation(self) -> None:
        """Circuit breaker trips independently for each session."""
        ctx_a = create_session_context(user_id="user_alice")
        ctx_b = create_session_context(user_id="user_bob")

        # Trip User A's circuit breaker by exceeding max_actions
        ctx_a.circuit_breaker.total_action_count = 50
        status_a = ctx_a.circuit_breaker.check_pre_execution("browser_navigate", {})
        assert status_a.tripped is True
        assert ctx_a.circuit_breaker.tripped is True

        # User B's circuit breaker must remain closed
        status_b = ctx_b.circuit_breaker.check_pre_execution("browser_navigate", {})
        assert status_b.tripped is False
        assert ctx_b.circuit_breaker.tripped is False

    def test_session_store_creates_isolated_computer_sessions(self) -> None:
        """InMemorySessionStore correctly instantiates separate SessionContext per user."""
        store = InMemorySessionStore()

        sess_a = store.get_or_create("sess_101", user_id="alice", domain="computer")
        sess_b = store.get_or_create("sess_102", user_id="bob", domain="computer")

        assert isinstance(sess_a, ComputerSession)
        assert isinstance(sess_b, ComputerSession)

        assert sess_a.session_context is not sess_b.session_context
        assert sess_a.session_context.vault is not sess_b.session_context.vault
        assert sess_a.session_context.user_id == "alice"
        assert sess_b.session_context.user_id == "bob"

    def test_redis_persistence_split_specification(self) -> None:
        """Only serializable logical fields are persisted; OS handles are reconstructed fresh."""
        ctx = create_session_context(user_id="user_alice", session_id="sess_split_test")
        ctx.computer_state.update(
            current_url="https://docs.python.org",
            active_application="chrome",
        )

        persisted = ctx.get_persisted_state()

        # Check persisted fields
        assert persisted["session_id"] == "sess_split_test"
        assert persisted["user_id"] == "user_alice"
        assert "computer_state" in persisted
        assert persisted["computer_state"]["current_url"] == "https://docs.python.org"
        assert persisted["computer_state"]["active_application"] == "chrome"

        # Verify live OS controller objects are NOT part of persisted dict
        assert "window_controller" not in persisted
        assert "browser_manager" not in persisted
        assert "app_controller" not in persisted
        assert "ui_automation" not in persisted

        # Simulate reconnect in a new process: reconstruct fresh context and restore logical state
        new_ctx = create_session_context(
            user_id="user_alice",
            session_id="sess_split_test",
            restored_logical_state=persisted,
        )

        assert new_ctx.computer_state.current_url == "https://docs.python.org"
        assert new_ctx.computer_state.active_application == "chrome"
        # Controllers are fresh new instances
        assert new_ctx.window_controller is not None
        assert new_ctx.browser_manager is not None
        assert new_ctx.window_controller is not ctx.window_controller

    def test_router_planner_llm_router_tool_registry_isolation(self) -> None:
        """Asserts router, planner, semantic_planner, llm_router, and tool_registry
        are constructed per session.
        """
        ctx_a = create_session_context(user_id="user_alice")
        ctx_b = create_session_context(user_id="user_bob")

        # 1. Router & Planner isolation
        assert ctx_a.router is not None
        assert ctx_b.router is not None
        assert ctx_a.router is not ctx_b.router

        assert ctx_a.planner is not None
        assert ctx_b.planner is not None
        assert ctx_a.planner is not ctx_b.planner
        assert ctx_a.router.planner is ctx_a.planner
        assert ctx_b.router.planner is ctx_b.planner

        # 2. Semantic Planner isolation
        assert ctx_a.semantic_planner is not None
        assert ctx_b.semantic_planner is not None
        assert ctx_a.semantic_planner is not ctx_b.semantic_planner

        # 3. Main LLM Router isolation
        assert ctx_a.llm_router is not None
        assert ctx_b.llm_router is not None
        assert ctx_a.llm_router is not ctx_b.llm_router
        assert ctx_a.agent.llm_router is ctx_a.llm_router
        assert ctx_b.agent.llm_router is ctx_b.llm_router

        # 4. Tool Registry isolation
        assert ctx_a.tool_registry is not None
        assert ctx_b.tool_registry is not None
        assert ctx_a.tool_registry is not ctx_b.tool_registry
        assert ctx_a.agent_harness.tool_registry is ctx_a.tool_registry
        assert ctx_b.agent_harness.tool_registry is ctx_b.tool_registry

        # 5. CareerSession isolation
        store = InMemorySessionStore()
        career_a = store.get_or_create("career_1", user_id="alice", domain="career")
        career_b = store.get_or_create("career_2", user_id="bob", domain="career")
        assert isinstance(career_a, CareerSession)
        assert isinstance(career_b, CareerSession)
        assert career_a.tool_registry is not career_b.tool_registry
        assert career_a.agent is not career_b.agent
        assert career_a.router is not career_b.router
        assert career_a.planner is not career_b.planner

    @pytest.mark.asyncio
    async def test_concurrent_orchestrator_message_handling(self) -> None:
        """Runs two sessions' message-handling concurrently via asyncio.gather
        to verify async safety and zero cross-talk.
        """
        settings = get_settings()
        store = InMemorySessionStore()

        sess_alice = store.get_or_create("sess_alice_001", user_id="user_alice", domain="computer")
        sess_bob = store.get_or_create("sess_bob_002", user_id="user_bob", domain="computer")

        orch_alice = JarvisOrchestrator(settings, session_store=store)
        orch_bob = JarvisOrchestrator(settings, session_store=store)

        events_alice: list[dict[str, Any]] = []
        events_bob: list[dict[str, Any]] = []

        async def send_alice(evt: dict[str, Any]) -> None:
            await asyncio.sleep(0.001)  # introduce slight scheduling interleaving
            events_alice.append(evt)

        async def send_bob(evt: dict[str, Any]) -> None:
            await asyncio.sleep(0.001)
            events_bob.append(evt)

        # Concurrently handle messages
        await asyncio.gather(
            orch_alice.handle_message(
                sess_alice, {"type": "chat", "text": "help"}, send=send_alice
            ),
            orch_bob.handle_message(
                sess_bob, {"type": "chat", "text": "help"}, send=send_bob
            ),
        )

        assert len(events_alice) > 0
        assert len(events_bob) > 0

        # Run IDs must be disjoint and mapped strictly to respective session prefixes
        run_ids_alice = {e.get("run_id") for e in events_alice if e.get("run_id")}
        run_ids_bob = {e.get("run_id") for e in events_bob if e.get("run_id")}
        assert run_ids_alice.isdisjoint(run_ids_bob)
        assert all("sess_ali" in str(rid) for rid in run_ids_alice)
        assert all("sess_bob" in str(rid) for rid in run_ids_bob)

        # Sequences must be strictly monotonic per session
        seqs_alice = [e["seq"] for e in events_alice]
        seqs_bob = [e["seq"] for e in events_bob]
        assert seqs_alice == sorted(set(seqs_alice))
        assert seqs_bob == sorted(set(seqs_bob))

        # Both sessions' session_context objects must remain completely separate
        assert sess_alice.session_context is not sess_bob.session_context
        assert sess_alice.session_context.user_id == "user_alice"
        assert sess_bob.session_context.user_id == "user_bob"

        # Test concurrent state updates and task manager increments
        async def work_alice() -> None:
            for i in range(10):
                sess_alice.computer_state.update(active_application=f"app_alice_{i}")
                sess_alice.task_manager.next_generation()
                await asyncio.sleep(0.001)

        async def work_bob() -> None:
            for i in range(10):
                sess_bob.computer_state.update(active_application=f"app_bob_{i}")
                sess_bob.task_manager.next_generation()
                await asyncio.sleep(0.001)

        await asyncio.gather(work_alice(), work_bob())

        assert sess_alice.computer_state.active_application == "app_alice_9"
        assert sess_bob.computer_state.active_application == "app_bob_9"
        assert sess_alice.task_manager.current_generation == 11
        assert sess_bob.task_manager.current_generation == 11
