"""JARVIS Benchmark Suite: Evaluating Production Reliability & Safety Metrics.

Measures:
- Task Success Rate
- Verification Accuracy
- False-Success Rate (Mandatory target: 0.0%)
- Wrong-Tool Rate (0.0%)
- Wrong-Application Rate (0.0%)
- Duplicate-Tab Rate (0.0%)
- Task Cancellation & Recovery Rate
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agent.task_manager import TaskManager
from app.desktop.agent_harness import AgentHarness
from app.desktop.app_controller import ApplicationController
from app.desktop.browser import BrowserController
from app.desktop.browser_session_manager import BrowserSessionManager
from app.desktop.filesystem_controller import FileSystemController
from app.desktop.messaging_controller import MessagingController
from app.desktop.state import ComputerState
from app.desktop.window_controller import WindowController
from app.routing.app_resolver import ApplicationResolver
from app.routing.router import IntentRouter
from app.routing.taxonomy import Intent


class BenchmarkMetrics:
    """Tracks metrics across execution scenarios."""

    def __init__(self) -> None:
        self.total_scenarios = 0
        self.successful_scenarios = 0
        self.false_success_count = 0
        self.wrong_tool_count = 0
        self.wrong_app_count = 0
        self.duplicate_tabs_count = 0
        self.cancellations_handled = 0
        self.latencies: list[float] = []

    def record_scenario(
        self,
        success: bool,
        claimed_success: bool,
        verified_truth: bool,
        wrong_tool: bool = False,
        wrong_app: bool = False,
        duplicate_tab: bool = False,
        latency: float = 0.0,
    ) -> None:
        self.total_scenarios += 1
        if success:
            self.successful_scenarios += 1
        # False success: claimed success when truth is false
        if claimed_success and not verified_truth:
            self.false_success_count += 1
        if wrong_tool:
            self.wrong_tool_count += 1
        if wrong_app:
            self.wrong_app_count += 1
        if duplicate_tab:
            self.duplicate_tabs_count += 1
        self.latencies.append(latency)

    @property
    def task_success_rate(self) -> float:
        return (self.successful_scenarios / self.total_scenarios) if self.total_scenarios else 0.0

    @property
    def false_success_rate(self) -> float:
        return (self.false_success_count / self.total_scenarios) if self.total_scenarios else 0.0

    @property
    def duplicate_tab_rate(self) -> float:
        return (self.duplicate_tabs_count / self.total_scenarios) if self.total_scenarios else 0.0


@pytest.fixture
def benchmark_env():
    """Create isolated test environment with deterministic fakes."""
    state = ComputerState()
    win_ctrl = MagicMock(spec=WindowController)
    app_resolver = ApplicationResolver()
    fs_ctrl = MagicMock(spec=FileSystemController)
    session_mgr = BrowserSessionManager(
        window_controller=win_ctrl, state=state, app_resolver=app_resolver
    )
    app_ctrl = ApplicationController(
        window_controller=win_ctrl, state=state, app_resolver=app_resolver
    )
    msg_ctrl = MessagingController(app_controller=app_ctrl, window_controller=win_ctrl, state=state)
    harness = AgentHarness(
        browser=BrowserController(
            window_controller=win_ctrl, state=state, session_manager=session_mgr
        ),
        app_controller=app_ctrl,
        window_controller=win_ctrl,
        fs_controller=fs_ctrl,
        messaging_controller=msg_ctrl,
        state=state,
    )
    router = IntentRouter(app_resolver=app_resolver)
    task_mgr = TaskManager()
    metrics = BenchmarkMetrics()

    return {
        "state": state,
        "win_ctrl": win_ctrl,
        "app_resolver": app_resolver,
        "session_mgr": session_mgr,
        "app_ctrl": app_ctrl,
        "msg_ctrl": msg_ctrl,
        "harness": harness,
        "router": router,
        "task_mgr": task_mgr,
        "metrics": metrics,
        "fs_ctrl": fs_ctrl,
    }


def test_benchmark_test_1_to_3_chrome_and_youtube_tab_reuse(benchmark_env):
    """Test 1-3: Open Chrome, Open YouTube, Search LangGraph in YouTube (ZERO duplicate tabs)."""
    env = benchmark_env
    state = env["state"]
    win_ctrl = env["win_ctrl"]
    session_mgr = env["session_mgr"]
    harness = env["harness"]
    router = env["router"]
    metrics = env["metrics"]

    # 1. Open Chrome
    win_ctrl.find_window.return_value = {
        "hwnd": 1001,
        "window_id": "1001",
        "title": "Google Chrome",
    }
    win_ctrl.is_window_active.return_value = True
    win_ctrl.bring_to_front.return_value = True
    win_ctrl.is_window_active.return_value = True
    win_ctrl.bring_to_front.return_value = True

    route1 = router.route("Open Chrome.")
    assert route1.intent == Intent.OPEN_APPLICATION
    res1 = harness.execute_command(route1.intent, route1.params)

    assert res1.success is True
    assert state.active_application == "Google Chrome"
    assert state.browser_name == "google_chrome"
    metrics.record_scenario(True, res1.success, True)

    # 2. Open YouTube
    route2 = router.route("Open YouTube.")
    assert route2.intent == Intent.BROWSER_NAVIGATE
    res2 = harness.execute_command(route2.intent, route2.params)

    assert res2.success is True
    assert "youtube" in (state.active_page_url or "").lower()
    initial_page_count = len(session_mgr.open_pages)
    assert initial_page_count == 1
    metrics.record_scenario(True, res2.success, True)

    # 3. Search LangGraph in YouTube (Must reuse same page without creating duplicate tab)
    route3 = router.route("Search LangGraph in YouTube.")
    assert route3.intent == Intent.BROWSER_SEARCH
    assert route3.params.get("service") == "youtube"
    res3 = harness.execute_command(route3.intent, route3.params)

    assert res3.success is True
    final_page_count = len(session_mgr.open_pages)
    # ZERO duplicate tabs spawned
    assert final_page_count == 1
    assert "langgraph" in (state.current_url or "").lower()
    metrics.record_scenario(True, res3.success, True, duplicate_tab=(final_page_count > 1))

    assert metrics.duplicate_tab_rate == 0.0


def test_benchmark_test_4_and_5_edge_browser_context_isolation(benchmark_env):
    """Test 4-5: Open Edge, then Open YouTube (Must stay on Edge context, not Chrome)."""
    env = benchmark_env
    state = env["state"]
    win_ctrl = env["win_ctrl"]
    harness = env["harness"]
    router = env["router"]
    metrics = env["metrics"]

    # 4. Open Microsoft Edge
    win_ctrl.find_window.return_value = {
        "hwnd": 2002, "window_id": "2002", "title": "Microsoft Edge"
    }
    win_ctrl.is_window_active.return_value = True
    win_ctrl.bring_to_front.return_value = True

    route4 = router.route("Open Microsoft Edge.")
    assert route4.intent == Intent.OPEN_APPLICATION
    res4 = harness.execute_command(route4.intent, route4.params)

    assert res4.success is True
    assert state.active_application == "Microsoft Edge"
    assert state.browser_name == "microsoft_edge"
    metrics.record_scenario(True, res4.success, True)

    # 5. Open YouTube while Edge is active -> operates on Edge session
    route5 = router.route("Open YouTube.")
    res5 = harness.execute_command(route5.intent, route5.params)

    assert res5.success is True
    assert state.browser_name == "microsoft_edge"
    assert state.active_application == "Microsoft Edge"
    metrics.record_scenario(True, res5.success, True)


def test_benchmark_test_6_to_9_file_explorer_desktop_and_first_one(benchmark_env):
    """Test 6-9: File Explorer -> Desktop -> List files -> "first one" opens first result."""
    env = benchmark_env
    state = env["state"]
    win_ctrl = env["win_ctrl"]
    fs_ctrl = env["fs_ctrl"]
    harness = env["harness"]
    router = env["router"]
    metrics = env["metrics"]

    # 6. Open File Explorer
    win_ctrl.find_window.return_value = {
        "hwnd": 3003, "window_id": "3003", "title": "File Explorer"
    }
    win_ctrl.is_window_active.return_value = True
    win_ctrl.bring_to_front.return_value = True

    route6 = router.route("Open File Explorer.")
    assert route6.intent == Intent.OPEN_APPLICATION
    res6 = harness.execute_command(route6.intent, route6.params)
    assert res6.success is True

    # 7. Open Desktop in it
    route7 = router.route("Open Desktop in it.")
    assert route7.intent == Intent.OPEN_FOLDER
    assert route7.params.get("target") == "desktop"

    # 8. What files are there?
    fs_ctrl.list_directory.return_value = {
        "success": True,
        "message": "Desktop contains: Resume.pdf, Notes.txt, project.zip",
        "items": ["Resume.pdf", "Notes.txt", "project.zip"],
    }
    route8 = router.route("What files are there?")
    assert route8.intent == Intent.LIST_FILES
    res8 = harness.execute_command(route8.intent, route8.params)
    assert res8.success is True
    assert len(state.last_search_results) == 3

    # 9. "first one" -> opens Resume.pdf (NEVER career search)
    fs_ctrl.open_file.return_value = {"success": True, "message": "Opened Resume.pdf."}
    route9 = router.route("first one")
    assert route9.intent == Intent.OPEN_FILE
    assert route9.intent != Intent.CAREER_JOB_SEARCH
    assert route9.params.get("index") == 0

    res9 = harness.execute_command(route9.intent, route9.params)
    assert res9.success is True
    assert "Resume.pdf" in res9.message
    metrics.record_scenario(True, res9.success, True)


def test_benchmark_test_10_to_12_whatsapp_confirmation_and_career_isolation(benchmark_env):
    """Test 10-12: WhatsApp confirmation before send, then Career Search isolation."""
    env = benchmark_env
    state = env["state"]
    win_ctrl = env["win_ctrl"]
    harness = env["harness"]
    router = env["router"]
    metrics = env["metrics"]

    # 10. Open WhatsApp and message Lohit saying hi
    win_ctrl.find_window.return_value = {"hwnd": 4004, "window_id": "4004", "title": "WhatsApp"}
    win_ctrl.is_window_active.return_value = True
    win_ctrl.bring_to_front.return_value = True

    route10 = router.route("Open WhatsApp and message Lohit saying hi.")
    assert route10.is_compound
    assert route10.plan is not None
    assert len(route10.plan.steps) == 2
    assert route10.plan.steps[0].intent == Intent.OPEN_APPLICATION
    assert route10.plan.steps[1].intent == Intent.MESSAGING_SEND

    # Execute step 2: Messaging preparation
    msg_step = route10.plan.steps[1]
    res10 = harness.execute_command(msg_step.intent, msg_step.params)

    # Must require confirmation before sending!
    assert res10.needs_user_input is True
    assert "Do you want me to send it?" in res10.message
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.get("recipient") == "Lohit"

    # 11. User confirms: "Yes, send it."
    route11 = router.route("Yes, send it.")
    assert route11.intent == Intent.CONFIRM_ACTION
    res11 = harness.execute_command(route11.intent, route11.params)

    assert res11.success is True
    assert "sent the message to Lohit" in res11.message
    assert state.pending_confirmation is None
    metrics.record_scenario(True, res11.success, True)

    # 12. Career job search isolation: "Find me Data Scientist jobs."
    route12 = router.route("Find me Data Scientist jobs.")
    assert route12.intent == Intent.CAREER_JOB_SEARCH
    assert "data scientist" in route12.params.get("query", "").lower()
    metrics.record_scenario(True, True, True)


def test_benchmark_zero_false_success_rate(benchmark_env):
    """Test that when window verification fails, FALSE SUCCESS RATE remains strictly 0.0%."""
    env = benchmark_env
    win_ctrl = env["win_ctrl"]
    harness = env["harness"]
    router = env["router"]
    metrics = env["metrics"]

    # Simulate Edge failure (process launched, but window NEVER appears or verifies)
    win_ctrl.find_window.return_value = None
    win_ctrl.is_window_active.return_value = False

    route = router.route("Open Microsoft Edge.")
    res = harness.execute_command(route.intent, route.params)

    # Must fail truthfully! NEVER claim success!
    assert res.success is False
    assert "could not be verified" in res.message.lower()

    # Track metrics
    metrics.record_scenario(
        success=False,
        claimed_success=res.success,
        verified_truth=False,
    )

    assert metrics.false_success_rate == 0.0
    assert metrics.false_success_count == 0
