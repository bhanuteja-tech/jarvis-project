"""Regression test suite for browser navigation, timeouts, idempotency, and multi-step flow.

Validates the 5 required regression scenarios:
1. TEST 1: Already at target URL -> NO navigation performed, immediate success.
2. TEST 2: Navigation times out, but observation confirms target reached -> SUCCESS.
3. TEST 3: "open youtube and search for LangGraph" flow -> navigate once, search, complete.
4. TEST 4: Navigation times out and URL remains old -> RECOVER or FAILED, never false success.
5. TEST 5: Task timeout -> circuit breaker trips cleanly per-task, resets cleanly for next task.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.computer.agent import ActionRecord, ComputerAgent
from app.computer.circuit_breaker import ActionCircuitBreaker
from app.desktop.agent_harness import HarnessResult
from app.desktop.browser import BrowserController
from app.desktop.browser_manager import BrowserManager


class MockBrowserController(BrowserController):
    def __init__(self) -> None:
        super().__init__()
        self.navigated_urls: list[str] = []
        self.searched_queries: list[str] = []
        self.navigate_timeout: bool = False

    def open_browser(self, url: str | None = None) -> tuple[bool, str]:
        target = url or "https://www.google.com"
        self._active_url = target
        self._history.append(target)
        self.navigated_urls.append(target)
        return True, f"Browser opened at {target}."

    def navigate(self, url: str) -> tuple[bool, str]:
        if self.navigate_timeout:
            return False, "Timed out waiting for page load"
        self._active_url = url
        self._history.append(url)
        self.navigated_urls.append(url)
        return True, f"Navigated to {url}."

    def search(self, query: str, engine: str = "google") -> tuple[bool, str]:
        self.searched_queries.append(query)
        target = f"https://www.youtube.com/results?search_query={query}"
        self._active_url = target
        self._history.append(target)
        return True, f"Searched for {query} on {engine}."


# ---------------------------------------------------------------------------
# TEST 1: Current URL is already target -> NO navigation, immediate success
# ---------------------------------------------------------------------------
def test_regression_test_1_already_at_target_idempotent() -> None:
    """TEST 1: If current URL is already https://www.youtube.com, skip navigation immediately."""
    bm = BrowserManager()
    bm.state.update(
        active_application="Google Chrome",
        current_url="https://www.youtube.com",
        active_window_title="YouTube",
    )
    win_info = {"hwnd": 1234, "window_id": "win_1", "title": "YouTube"}
    bm.find_browser_window = MagicMock(return_value=win_info)
    bm.window_controller.bring_to_front = MagicMock(return_value=True)

    with patch.object(bm, "open_browser") as mock_open:
        ok, msg = bm.navigate("https://www.youtube.com")
        assert ok is True
        assert "already open and active" in msg
        mock_open.assert_not_called()


@pytest.mark.asyncio
async def test_regression_test_1_agent_execute_tool_idempotent() -> None:
    """TEST 1 (Agent level): Agent recognizes already-at-target before calling harness."""
    agent = ComputerAgent()
    agent.state.update(
        active_application="Google Chrome",
        current_url="https://www.youtube.com",
        active_window_title="YouTube",
    )

    with patch.object(agent.harness, "execute_command") as mock_exec:
        result = await agent._execute_tool(
            "browser_navigate",
            {"url": "https://www.youtube.com"},
        )
        assert result.get("success") is True
        assert result.get("already_at_target") is True
        mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# TEST 2: Navigation timeout but observation confirms target reached -> SUCCESS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regression_test_2_navigation_timeout_observation_success() -> None:
    """TEST 2: If browser navigation times out, but observation shows YouTube, treat as SUCCESS."""
    agent = ComputerAgent()
    agent.state.update(
        active_application="Google Chrome",
        current_url="https://www.google.com",
        active_window_title="Google",
    )

    obs_after = {
        "active_application": "Google Chrome",
        "current_url": "https://www.youtube.com",
        "active_window_title": "YouTube",
    }

    mock_harness_res = HarnessResult(
        success=False,
        message="Navigation timed out after 15s waiting for networkidle",
        action="navigate",
        details={},
    )

    with patch.object(agent.harness, "execute_command", return_value=mock_harness_res), \
         patch.object(agent.observer, "observe", return_value=obs_after):
        result = await agent._execute_tool(
            "browser_navigate",
            {"url": "https://www.youtube.com"},
        )

        assert result.get("success") is True
        assert result.get("recovered_from_timeout") is True


# ---------------------------------------------------------------------------
# TEST 3: Multi-step "open youtube and search for LangGraph"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regression_test_3_compound_youtube_search_flow() -> None:
    """TEST 3: Multi-step execution for 'open youtube and search for LangGraph'.

    Progression:
    1. Blank state -> decides browser_navigate("https://www.youtube.com")
    2. YouTube state -> decides browser_search(query="LangGraph", site="youtube")
    3. Search results state -> decides complete
    No repeated browser navigation occurs.
    """
    agent = ComputerAgent()
    user_goal = "open youtube and search for LangGraph"

    # Step 1: Initial state (desktop)
    agent.state.update(
        active_application="Desktop",
        current_url="",
        active_window_title="Desktop",
    )
    decision1, _ = await agent._decide_next_action(user_goal)
    assert decision1.get("decision") == "tool_call"
    assert decision1.get("tool") == "browser_navigate"
    assert "youtube.com" in decision1.get("arguments", {}).get("url", "")

    # Step 2: YouTube homepage is open
    agent.state.update(
        active_application="Google Chrome",
        current_url="https://www.youtube.com",
        active_window_title="YouTube",
    )
    decision2, _ = await agent._decide_next_action(user_goal)
    assert decision2.get("decision") == "tool_call"
    assert decision2.get("tool") == "browser_search"
    assert decision2.get("arguments", {}).get("query") == "LangGraph"
    assert decision2.get("arguments", {}).get("site") == "youtube"

    # Step 3: Search action completed and verified
    search_action = ActionRecord(
        step_id="step_1",
        tool="browser_search",
        arguments={"query": "LangGraph", "site": "youtube"},
        result={"success": True},
        observation={"current_url": "https://www.youtube.com/results?search_query=LangGraph"},
        verified=True,
    )
    decision3, _ = await agent._decide_next_action(user_goal, turn_actions=[search_action])
    assert decision3.get("decision") == "complete"
    assert "LangGraph" in decision3.get("response", "")


# ---------------------------------------------------------------------------
# TEST 4: Navigation timeout where URL remains old -> RECOVER or FAILED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regression_test_4_navigation_timeout_url_remains_old_fails() -> None:
    """TEST 4: When navigation times out and URL remains old, it must NEVER falsely succeed."""
    agent = ComputerAgent()
    agent.state.update(
        active_application="Google Chrome",
        current_url="https://www.google.com",
        active_window_title="Google",
    )

    obs_after = {
        "active_application": "Google Chrome",
        "current_url": "https://www.google.com",
        "active_window_title": "Google",
    }

    mock_harness_res = HarnessResult(
        success=False,
        message="Navigation timed out after 15s",
        action="navigate",
        details={},
    )

    with patch.object(agent.harness, "execute_command", return_value=mock_harness_res), \
         patch.object(agent.observer, "observe", return_value=obs_after):
        result = await agent._execute_tool(
            "browser_navigate",
            {"url": "https://www.youtube.com"},
        )

        # Must report failure
        assert result.get("success") is False
        assert result.get("recovered_from_timeout") is not True

        # And verifier must also reject
        ver = agent._verify_action(
            tool_name="browser_navigate",
            arguments={"url": "https://www.youtube.com"},
            harness_result=result,
            observation=obs_after,
            task_id="task_1",
            generation=1,
            user_goal="open youtube and search for LangGraph",
        )
        assert ver.success is False


# ---------------------------------------------------------------------------
# TEST 5: Task timeout and circuit breaker session isolation
# ---------------------------------------------------------------------------
def test_regression_test_5_task_timeout_per_task_calibration() -> None:
    """TEST 5: ActionCircuitBreaker measures elapsed time from task start, not session creation.

    Tripped status resets cleanly between tasks, preventing repeated false timeouts.
    """
    cb = ActionCircuitBreaker(task_timeout_seconds=60.0)

    # Simulate an old session that has been open for 120 seconds
    cb.start_time = time.perf_counter() - 120.0

    # Without reset, check_pre_execution would trip with 120s!
    status_stale = cb.check_pre_execution("browser_navigate", {}, "Desktop")
    assert status_stale.tripped is True
    assert "120" in status_stale.reason or "limit 60.0s" in status_stale.reason

    # Now reset for a new task
    cb.reset_for_task(task_timeout_seconds=60.0)

    # Immediately check: elapsed is ~0.0s, tripped is False
    status_fresh = cb.check_pre_execution("browser_navigate", {}, "Desktop")
    assert status_fresh.tripped is False
    assert cb.tripped is False
    assert cb.task_timeout_seconds == 60.0
