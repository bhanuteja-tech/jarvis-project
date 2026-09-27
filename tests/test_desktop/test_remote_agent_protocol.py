"""Tests for Step 4: Remote Agent Protocol, Session Namespacing, and Confirmation Guard."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.computer.session_context import create_session_context
from app.config.settings import Settings
from app.desktop.dispatcher import (
    ActionCancelledError,
    ActionTimeoutError,
    NoRemoteAgentConnectedError,
    RemoteAgentDispatcher,
)
from app.jarvis.events import ActionResultPayload
from app.main import create_app
from jarvis_agent.client import JarvisAgentClient
from jarvis_agent.confirmation import MockConfirmationHandler
from jarvis_agent.models import ActionRequest


class TestRemoteAgentDispatcherGating:
    """Verifies Requirement #1: Standalone fallback gating via
    JARVIS_ALLOW_LOCAL_EXECUTION_FALLBACK.
    """

    @pytest.mark.asyncio
    async def test_dispatcher_fails_safe_when_remote_agent_missing_and_flag_off(self) -> None:
        """With flag off (default) and no remote agent, action dispatch fails safe
        with zero OS execution.
        """
        settings = Settings(jarvis_allow_local_execution_fallback=False)
        ctx = create_session_context(user_id="user_test_1")

        mock_harness = MagicMock()
        ctx.agent_harness = mock_harness
        ctx.agent_ws = None  # No remote agent connected

        dispatcher = RemoteAgentDispatcher(session_context=ctx, settings=settings)

        with pytest.raises(NoRemoteAgentConnectedError) as exc_info:
            await dispatcher.dispatch_action(
                step_id="step_1",
                tool="open_application",
                params={"application": "Visual Studio Code"},
            )

        assert "Direct server-side execution is prohibited by policy" in str(exc_info.value)
        # Assert local OS harness was never called
        mock_harness.execute_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatcher_allows_local_execution_when_explicitly_opted_in(self) -> None:
        """With flag on (local dev only), dispatcher falls back to local execution."""
        settings = Settings(jarvis_allow_local_execution_fallback=True)
        ctx = create_session_context(user_id="user_test_2")

        mock_harness = MagicMock()
        mock_harness.execute_command.return_value = MagicMock(
            success=True, message="App launched", details={"pid": 9999}
        )
        ctx.agent_harness = mock_harness
        ctx.agent_ws = None

        dispatcher = RemoteAgentDispatcher(session_context=ctx, settings=settings)

        res = await dispatcher.dispatch_action(
            step_id="step_2",
            tool="open_application",
            params={"application": "Google Chrome"},
        )

        assert res.success is True
        assert res.message == "App launched"
        mock_harness.execute_command.assert_called_once_with(
            "open_application", {"application": "Google Chrome"}
        )


class TestSessionBoundActionNamespacingAndTransportInvariant:
    """Verifies Requirement #2: pending_actions stored on SessionContext
    and transport-level enforcement.
    """

    @pytest.mark.asyncio
    async def test_action_id_stored_in_session_context(self) -> None:
        """action_id is strictly registered in SessionContext.pending_actions."""
        ctx = create_session_context(user_id="user_alice")
        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.closed = False
        ctx.agent_ws = mock_ws

        dispatcher = RemoteAgentDispatcher(session_context=ctx)

        # Launch dispatch in background task
        dispatch_task = asyncio.create_task(
            dispatcher.dispatch_action(
                step_id="step_10",
                tool="focus_application",
                params={"application": "Spotify"},
                timeout_seconds=5.0,
            )
        )

        # Allow task to register action
        await asyncio.sleep(0.01)

        # Assert action_id is inside ctx.pending_actions
        assert len(ctx.pending_actions) == 1
        action_id = list(ctx.pending_actions.keys())[0]
        assert action_id.startswith("act_")

        # Resolve the pending future
        fut = ctx.pending_actions[action_id]
        fut.set_result(
            ActionResultPayload(
                action_id=action_id,
                step_id="step_10",
                success=True,
                message="Focused",
            )
        )

        result = await dispatch_task
        assert result.success is True
        assert result.message == "Focused"
        # Pending actions cleaned up in finally block
        assert len(ctx.pending_actions) == 0

    def test_transport_invariant_rejects_action_result_from_unauthorized_connection(self) -> None:
        """Assert action_result from non-agent connection is rejected at transport level."""
        settings = Settings(
            jarvis_allow_unauthenticated=True,
            jarvis_allow_local_execution_fallback=False,
        )
        app = create_app(settings)
        client = TestClient(app)

        session_id = "test_shared_sess"

        # Connection 1: standard user UI connection (not agent)
        with client.websocket_connect(f"/ws/jarvis?session_id={session_id}") as ui_ws:
            # Attempt to send an action_result from non-agent connection
            ui_ws.send_json({
                "type": "action_result",
                "action_id": "act_spoof_123",
                "success": True,
            })
            frame = ui_ws.receive_json()
            assert frame["type"] == "error"
            assert frame["data"]["code"] == "unauthorized_agent_connection"

    def test_protocol_rejects_unrecognized_or_cross_session_action_id(self) -> None:
        """Assert agent connection sending unknown/unissued action_id
        receives invalid_action_id error.
        """
        settings = Settings(
            jarvis_allow_unauthenticated=True,
            jarvis_allow_local_execution_fallback=False,
        )
        app = create_app(settings)
        client = TestClient(app)

        session_id = "test_agent_sess"

        # Connect as jarvis_agent
        with client.websocket_connect(
            f"/ws/jarvis?session_id={session_id}&client_type=agent"
        ) as agent_ws:
            # Send action_result for action_id not in session pending_actions
            agent_ws.send_json({
                "type": "action_result",
                "action_id": "act_random_unissued",
                "success": True,
            })
            frame = agent_ws.receive_json()
            assert frame["type"] == "error"
            assert frame["data"]["code"] == "invalid_action_id"


class TestConfirmationGuardThroughProtocol:
    """Verifies Requirement #3: Threading confirmation guard through action_request."""

    @pytest.mark.asyncio
    async def test_destructive_action_declined_by_local_user_fails_safe(self) -> None:
        """When local confirmation handler returns False, action is declined and tool is not run."""
        mock_handler = MockConfirmationHandler(approve=False)
        mock_local_harness = MagicMock()

        agent_client = JarvisAgentClient(
            server_ws_url="ws://localhost:8000/ws/jarvis",
            session_id="sess_conf_1",
            access_token="fake-token",
            confirmation_handler=mock_handler,
            local_harness=mock_local_harness,
        )

        request = ActionRequest(
            action_id="act_delete_files",
            session_id="sess_conf_1",
            step_id="step_destructive",
            tool="send_message",
            params={"recipient": "boss", "message": "I quit"},
            requires_confirmation=True,
            confirmation_prompt="Confirm sending resignation message?",
            confirmation_timeout_seconds=60.0,
        )

        res = await agent_client.execute_action_request(request)

        assert mock_handler.call_count == 1
        assert res.success is False
        assert res.cancelled is True
        assert "Action declined by user" in res.message
        # Crucial check: local tool execution was never invoked
        mock_local_harness.execute_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_destructive_action_approved_by_local_user_executes(self) -> None:
        """When local confirmation handler returns True, action execution proceeds."""
        mock_handler = MockConfirmationHandler(approve=True)
        mock_local_harness = MagicMock()
        mock_local_harness.execute_command.return_value = MagicMock(
            success=True, message="Message sent", details={"msg_id": "m123"}
        )

        agent_client = JarvisAgentClient(
            server_ws_url="ws://localhost:8000/ws/jarvis",
            session_id="sess_conf_2",
            access_token="fake-token",
            confirmation_handler=mock_handler,
            local_harness=mock_local_harness,
        )

        request = ActionRequest(
            action_id="act_send_msg",
            session_id="sess_conf_2",
            step_id="step_send",
            tool="send_message",
            params={"recipient": "friend", "message": "Hello"},
            requires_confirmation=True,
            confirmation_prompt="Confirm sending message?",
        )

        res = await agent_client.execute_action_request(request)

        assert mock_handler.call_count == 1
        assert res.success is True
        assert res.message == "Message sent"
        mock_local_harness.execute_command.assert_called_once_with(
            "send_message", {"recipient": "friend", "message": "Hello"}
        )


class TestTimeoutAndTokenLifecycle:
    """Verifies Requirement #4: In-flight timeout and proactive token refresh."""

    @pytest.mark.asyncio
    async def test_action_timeout_cleans_up_pending_future(self) -> None:
        """When an action times out, ActionTimeoutError is raised and pending_actions is purged."""
        ctx = create_session_context(user_id="user_timeout")
        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.closed = False
        ctx.agent_ws = mock_ws

        settings = Settings(jarvis_remote_action_timeout_seconds=0.1)
        dispatcher = RemoteAgentDispatcher(session_context=ctx, settings=settings)

        with pytest.raises(ActionTimeoutError):
            await dispatcher.dispatch_action(
                step_id="step_slow",
                tool="browser_navigate",
                params={"url": "https://slow-site.example"},
                timeout_seconds=0.05,
            )

        # Assert no memory leak: future is removed
        assert len(ctx.pending_actions) == 0

    @pytest.mark.asyncio
    async def test_agent_client_token_refresh(self) -> None:
        """JarvisAgentClient successfully updates its access_token via refresh endpoint."""
        agent_client = JarvisAgentClient(
            server_ws_url="ws://localhost:8000/ws/jarvis",
            session_id="sess_token_test",
            access_token="old_access_token",
            refresh_token="valid_refresh_token",
            auth_base_url="http://mocked-auth",
        )

        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "new_refreshed_access_token",
                "refresh_token": "new_refreshed_refresh_token",
            },
        )

        from unittest.mock import patch
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            success = await agent_client.refresh_access_token()

        assert success is True
        assert agent_client.access_token == "new_refreshed_access_token"
        assert agent_client.refresh_token == "new_refreshed_refresh_token"

    def test_agent_client_device_id_persistence_and_url(self, tmp_path: Path) -> None:
        """JarvisAgentClient generates and persists device_id and includes it in ws_url."""
        from jarvis_agent.client import get_or_create_device_id

        dev_file = tmp_path / "device_id"
        id1 = get_or_create_device_id(dev_file)
        assert id1.startswith("dev_")

        # Second call returns same ID
        id2 = get_or_create_device_id(dev_file)
        assert id2 == id1

        # JarvisAgentClient uses provided or persistent device ID in build_ws_url
        client = JarvisAgentClient(
            server_ws_url="ws://localhost:8000/ws/jarvis",
            session_id="sess_dev_test",
            access_token="tok_123",
            device_id=id1,
        )
        url = client.build_ws_url()
        assert f"device_id={id1}" in url
        assert "client_type=agent" in url


class TestAgentDisconnectionAndReconnectionRecovery:
    """Verifies disconnect grace period, reconnect replan, and duplicate rejection."""

    @pytest.fixture(autouse=True)
    def setup_stores(self) -> None:
        from app.api.routes.jarvis import reset_stores_for_tests

        reset_stores_for_tests()

    def test_transient_disconnect_within_grace_period_does_not_cancel_action(self) -> None:
        """Transient disconnect within grace period does not fail in-flight action."""
        import time

        settings = Settings(
            jarvis_allow_unauthenticated=True,
            jarvis_disconnect_grace_period_seconds=2.0,
        )
        app = create_app(settings)
        session_id = "test_transient_sess"

        with TestClient(app) as client:
            # 1. Connect agent
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent"
            ):
                from app.api.routes.jarvis import _session_store

                sess = _session_store.get(session_id)
                assert sess is not None
                ctx = sess.session_context
                assert ctx.agent_ws is not None

                # Register an in-flight pending action
                loop = asyncio.new_event_loop()
                fut = loop.create_future()
                ctx.pending_actions["act_transient_1"] = fut

            # ws1 is now disconnected!
            for _ in range(50):
                if ctx.agent_ws is None and ctx.disconnect_timer is not None:
                    break
                time.sleep(0.02)

            assert ctx.agent_ws is None
            assert not fut.done()
            assert ctx.disconnect_timer is not None

            # 2. Reconnect agent before 2.0s grace period expires
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent"
            ) as ws2:
                assert ctx.agent_ws is not None
                # Disconnect timer was cancelled
                assert ctx.disconnect_timer is None
                assert not fut.done()

                # Resolve the action from the reconnected agent
                ws2.send_json({
                    "type": "action_result",
                    "action_id": "act_transient_1",
                    "success": True,
                    "message": "Finished after reconnect",
                })
                for _ in range(50):
                    if fut.done():
                        break
                    time.sleep(0.02)
                assert fut.done()
                assert fut.result().success is True
                assert fut.result().message == "Finished after reconnect"

    def test_disconnect_past_grace_period_cancels_action(self) -> None:
        """When grace period expires without reconnection, in-flight action is cancelled."""
        import time

        settings = Settings(
            jarvis_allow_unauthenticated=True,
            jarvis_disconnect_grace_period_seconds=0.1,
        )
        app = create_app(settings)
        session_id = "test_expire_sess"

        with TestClient(app) as client:
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent"
            ):
                from app.api.routes.jarvis import _session_store

                sess = _session_store.get(session_id)
                assert sess is not None
                ctx = sess.session_context

                loop = asyncio.new_event_loop()
                fut = loop.create_future()
                ctx.pending_actions["act_expired_1"] = fut

            # ws1 closed, wait for 0.1s grace period to expire
            for _ in range(50):
                if fut.done():
                    break
                time.sleep(0.02)

            assert fut.done()
            with pytest.raises(ActionCancelledError) as exc_info:
                fut.result()
            assert "grace period" in str(exc_info.value)
            assert len(ctx.pending_actions) == 0

    def test_duplicate_agent_registration_rejected_leaving_first_bound(self) -> None:
        """Second connection attempting to register as agent while active is rejected."""
        settings = Settings(jarvis_allow_unauthenticated=True)
        app = create_app(settings)
        session_id = "test_dup_agent_sess"

        with TestClient(app) as client:
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent"
            ):
                from app.api.routes.jarvis import _session_store

                sess = _session_store.get(session_id)
                assert sess is not None
                ctx = sess.session_context
                assert ctx.agent_ws is not None

                # Attempt second agent connection
                with client.websocket_connect(
                    f"/ws/jarvis?session_id={session_id}&client_type=agent"
                ) as ws2:
                    frame = ws2.receive_json()
                    assert frame["type"] == "error"
                    assert frame["data"]["code"] == "duplicate_agent_registration"
                    assert "Takeover rejected" in frame["data"]["message"]

                # Assert first agent connection remains bound and undisturbed
                assert ctx.agent_ws is not None

    def test_different_device_same_user_cannot_claim_reconnect_slot(self) -> None:
        """Device B under same user account cannot hijack Device A's disconnect grace slot."""
        import time

        settings = Settings(
            jarvis_allow_unauthenticated=True,
            jarvis_disconnect_grace_period_seconds=2.0,
        )
        app = create_app(settings)
        session_id = "test_device_hijack_sess"

        with TestClient(app) as client:
            # 1. Device A connects and registers an in-flight pending action
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent&device_id=dev_laptop_A"
            ):
                from app.api.routes.jarvis import _session_store

                sess = _session_store.get(session_id)
                assert sess is not None
                ctx = sess.session_context
                assert ctx.agent_ws is not None
                assert ctx.agent_device_id == "dev_laptop_A"

                loop = asyncio.new_event_loop()
                fut = loop.create_future()
                ctx.pending_actions["act_device_a_1"] = fut

            # Device A has disconnected, grace timer is running
            for _ in range(50):
                if ctx.agent_ws is None and ctx.disconnect_timer is not None:
                    break
                time.sleep(0.02)

            assert ctx.agent_ws is None
            assert ctx.disconnect_timer is not None
            assert ctx.agent_device_id == "dev_laptop_A"
            assert not fut.done()

            # 2. Device B (same user/session, different device_id) attempts to bind within grace
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent&device_id=dev_desktop_B"
            ) as ws_b:
                frame = ws_b.receive_json()
                assert frame["type"] == "error"
                assert frame["data"]["code"] == "duplicate_agent_registration"
                assert "reserved for device 'dev_laptop_A'" in frame["data"]["message"]

            # Verify Device B was rejected: slot still belongs to Device A, action still pending
            assert ctx.agent_ws is None
            assert ctx.agent_device_id == "dev_laptop_A"
            assert not fut.done()

            # 3. Device A reconnects with its legitimate device_id before grace expires
            with client.websocket_connect(
                f"/ws/jarvis?session_id={session_id}&client_type=agent&device_id=dev_laptop_A"
            ) as ws_a:
                assert ctx.agent_ws is not None
                assert ctx.disconnect_timer is None
                assert not fut.done()

                # Device A resolves its in-flight action
                ws_a.send_json({
                    "type": "action_result",
                    "action_id": "act_device_a_1",
                    "success": True,
                    "message": "Device A completed operation",
                })
                for _ in range(50):
                    if fut.done():
                        break
                    time.sleep(0.02)

                assert fut.done()
                assert fut.result().success is True
                assert fut.result().message == "Device A completed operation"

    def test_agent_reconnect_resumes_verified_state_and_replans(self) -> None:
        """Session preserves verified ComputerState and drops stale actions on reconnect."""
        import time

        from app.api.routes.jarvis import _session_store

        session_id = "test_replan_sess"
        sess = _session_store.get_or_create(session_id, domain="computer")
        ctx = sess.session_context

        # Set verified state
        ctx.computer_state.active_application = "Visual Studio Code"
        ctx.computer_state.current_directory = "C:\\Projects\\repo"
        ctx.computer_state.last_action = "open_folder"

        # Simulate interrupted action
        loop = asyncio.new_event_loop()
        ctx.pending_actions["stale_act"] = loop.create_future()

        # Save session to store
        _session_store.save(sess)

        # Drop stale action on session reload
        ctx.pending_actions.clear()

        # Reconnect agent
        settings = Settings(jarvis_allow_unauthenticated=True)
        app = create_app(settings)
        client = TestClient(app)

        with client.websocket_connect(
            f"/ws/jarvis?session_id={session_id}&client_type=agent"
        ) as ws:
            loaded_sess = _session_store.get(session_id)
            assert loaded_sess is not None
            loaded_ctx = loaded_sess.session_context

            # Verified state preserved from persistent store
            assert loaded_ctx.computer_state.active_application == "Visual Studio Code"
            assert loaded_ctx.computer_state.current_directory == "C:\\Projects\\repo"
            assert loaded_ctx.computer_state.last_action == "open_folder"

            # No stale actions remain
            assert len(loaded_ctx.pending_actions) == 0

            # Fresh action can be dispatched and executed on reconnect
            new_fut = loop.create_future()
            loaded_ctx.pending_actions["new_act"] = new_fut
            ws.send_json({
                "type": "action_result",
                "action_id": "new_act",
                "success": True,
                "message": "Observed and executed",
            })
            for _ in range(50):
                if new_fut.done():
                    break
                time.sleep(0.02)
            assert new_fut.done()
            assert new_fut.result().success is True
            assert new_fut.result().message == "Observed and executed"
