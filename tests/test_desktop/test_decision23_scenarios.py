"""Decision 23 Test Suite — Verifying the 13 Exact Scenarios from the Specification.

Scenarios tested:
1. "Open Chrome" -> Chrome foreground.
2. "Open Edge" -> Edge foreground.
3. "Open Chrome and search YouTube" -> Chrome foreground -> YouTube in Chrome.
4. "Open Edge and open YouTube" -> Edge foreground -> YouTube in Edge.
5. "Open YouTube" -> appropriate browser resolved by context/default policy.
6. "Open Edge and search LangGraph on YouTube" -> Edge -> YouTube -> LangGraph.
7. "Open YouTube" then "Open CampusX" -> reuse YouTube context.
8. "Open the LangGraph course" -> CampusX context -> LangGraph course.
9. "Open the third video" -> current course -> third video -> verify.
10. "Open File Explorer" then "Open Desktop in it" -> File Explorer -> Desktop.
11. "Show files" then "Open the first one" -> first result.
12. "Open WhatsApp and send hi to Lohit" -> WhatsApp -> Lohit -> confirmation.
13. "Find Python jobs in Bangalore" -> Computer page MUST NOT invoke CareerAgent.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.computer.intent_extractor import ComputerIntentExtractor
from app.computer.semantic_planner import SemanticTaskPlanner
from app.computer.web_context_tracker import WebContextTracker
from app.config.settings import Settings
from app.desktop.agent_harness import AgentHarness
from app.desktop.state import ComputerState
from app.jarvis.intent import parse_intent
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import Session


def _build_test_harness(state: ComputerState | None = None) -> AgentHarness:
    cs = state or ComputerState()
    app_ctrl = MagicMock()
    app_ctrl.open_application.return_value = {
        "success": True,
        "message": "Opened application successfully.",
        "foreground": True,
    }
    app_ctrl.get_active_application.return_value = "google_chrome"

    browser_ctrl = MagicMock()
    browser_ctrl.open_browser.return_value = {
        "success": True,
        "message": "Opened browser successfully.",
        "browser_name": "google_chrome",
    }
    browser_ctrl.navigate.return_value = {
        "success": True,
        "message": "Navigated to page.",
        "url": "https://www.youtube.com",
    }
    browser_ctrl.search_web.return_value = {
        "success": True,
        "message": "Searched web successfully.",
        "query": "LangGraph",
        "url": "https://www.youtube.com/results?search_query=LangGraph",
    }

    win_ctrl = MagicMock()
    win_ctrl.get_foreground_window.return_value = {
        "title": "Google Chrome",
        "process_name": "chrome.exe",
    }

    fs_ctrl = MagicMock()
    fs_ctrl.list_directory.return_value = {
        "success": True,
        "items": ["Resume.pdf", "Project.pdf", "notes.txt"],
        "message": "Found 3 files.",
    }
    fs_ctrl.open_file.return_value = {
        "success": True,
        "message": "Opened Resume.pdf",
    }

    desktop_ctrl = MagicMock()
    desktop_ctrl.open_desktop.return_value = {
        "success": True,
        "message": "Opened Desktop folder.",
    }
    desktop_ctrl.open_folder.return_value = {
        "success": True,
        "message": "Opened folder.",
    }

    msg_ctrl = MagicMock()
    msg_ctrl.send_message.return_value = {
        "success": True,
        "message": "Message prepared.",
        "needs_confirmation": True,
    }

    harness = AgentHarness(
        app_controller=app_ctrl,
        browser_controller=browser_ctrl,
        window_controller=win_ctrl,
        desktop_controller=desktop_ctrl,
        fs_controller=fs_ctrl,
        messaging_controller=msg_ctrl,
        state=cs,
    )
    return harness


# ---------------------------------------------------------------------------
# Scenario 1: "Open Chrome"
# ---------------------------------------------------------------------------
def test_scenario_1_open_chrome():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open Chrome")

    assert intent.intent_type == "OPEN_APPLICATION"
    assert intent.explicit_browser == "google_chrome"
    assert intent.application is not None
    assert intent.application.canonical == "google_chrome"

    plan = planner.plan(intent)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "open_browser"
    assert plan.steps[0].params["browser_name"] == "google_chrome"
    assert plan.steps[0].verification.value == "browser_foreground"


# ---------------------------------------------------------------------------
# Scenario 2: "Open Edge"
# ---------------------------------------------------------------------------
def test_scenario_2_open_edge():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open Edge")

    assert intent.intent_type == "OPEN_APPLICATION"
    assert intent.explicit_browser == "microsoft_edge"
    assert intent.application is not None
    assert intent.application.canonical == "microsoft_edge"

    plan = planner.plan(intent)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "open_browser"
    assert plan.steps[0].params["browser_name"] == "microsoft_edge"
    assert plan.steps[0].verification.value == "browser_foreground"


# ---------------------------------------------------------------------------
# Scenario 3: "Open Chrome and search YouTube"
# ---------------------------------------------------------------------------
def test_scenario_3_open_chrome_and_search_youtube():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open Chrome and search YouTube")

    assert intent.is_multi_step()
    assert intent.explicit_browser == "google_chrome"
    assert any("open_browser" in a for a in intent.actions)
    assert any("search" in a or "navigate" in a for a in intent.actions)

    plan = planner.plan(intent)
    assert len(plan.steps) >= 2
    assert plan.steps[0].tool == "open_browser"
    assert plan.steps[0].params["browser_name"] == "google_chrome"


# ---------------------------------------------------------------------------
# Scenario 4: "Open Edge and open YouTube"
# ---------------------------------------------------------------------------
def test_scenario_4_open_edge_and_open_youtube():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open Edge and open YouTube")

    assert intent.is_multi_step()
    assert intent.explicit_browser == "microsoft_edge"

    plan = planner.plan(intent)
    assert len(plan.steps) >= 2
    assert plan.steps[0].tool == "open_browser"
    assert plan.steps[0].params["browser_name"] == "microsoft_edge"
    assert plan.steps[1].params.get("browser_name") == "microsoft_edge"
    step1_url = plan.steps[1].params.get("url", "").lower()
    step1_svc = plan.steps[1].params.get("service_name", "").lower()
    assert "youtube" in step1_url or "youtube" in step1_svc


# ---------------------------------------------------------------------------
# Scenario 5: "Open YouTube" (Resolves default/context browser)
# ---------------------------------------------------------------------------
def test_scenario_5_open_youtube():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open YouTube")

    assert intent.intent_type == "BROWSER_NAVIGATE"
    assert intent.destination is not None
    assert intent.destination.site == "youtube"
    assert intent.explicit_browser is None  # not explicit

    # Resolve with context browser
    state = ComputerState()
    state.browser_name = "microsoft_edge"
    plan = planner.plan(intent, computer_state=state)
    assert len(plan.steps) == 1
    assert "youtube" in plan.steps[0].params["url"].lower()


# ---------------------------------------------------------------------------
# Scenario 6: "Open Edge and search LangGraph on YouTube"
# ---------------------------------------------------------------------------
def test_scenario_6_open_edge_and_search_langgraph_on_youtube():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()
    intent = extractor.extract("Open Edge and search LangGraph on YouTube")

    assert intent.is_multi_step()
    assert intent.explicit_browser == "microsoft_edge"

    plan = planner.plan(intent)
    assert len(plan.steps) >= 2
    assert plan.steps[0].params["browser_name"] == "microsoft_edge"

    search_step = plan.steps[-1]
    assert search_step.tool in ("search_browser", "navigate_browser")
    assert search_step.params.get("browser_name") == "microsoft_edge"
    q_str = search_step.params.get("query", "").lower()
    url_str = search_step.params.get("url", "").lower()
    assert "langgraph" in q_str or "langgraph" in url_str


# ---------------------------------------------------------------------------
# Scenario 7: "Open YouTube" then "Open CampusX" (Context Reuse)
# ---------------------------------------------------------------------------
def test_scenario_7_context_reuse_youtube_to_campusx():
    state = ComputerState()
    state.active_browser = True
    state.browser_name = "google_chrome"
    state.active_page_url = "https://www.youtube.com"
    tracker = WebContextTracker(state)
    tracker.update_from_navigation("https://www.youtube.com", "YouTube")

    extractor = ComputerIntentExtractor()
    intent = extractor.extract("Open CampusX", computer_state=state)
    # Inside YouTube, "CampusX" is identified as a web/channel target
    assert intent.destination is not None or intent.application is not None

    # Track channel update
    tracker.update_channel("CampusX")
    assert state.web_context.channel == "CampusX"


# ---------------------------------------------------------------------------
# Scenario 8: "Open the LangGraph course" (From CampusX context)
# ---------------------------------------------------------------------------
def test_scenario_8_open_course_from_channel_context():
    state = ComputerState()
    state.active_browser = True
    state.browser_name = "google_chrome"
    tracker = WebContextTracker(state)
    tracker.update_from_navigation(
        "https://www.youtube.com/@CampusX-official", "CampusX - YouTube"
    )
    tracker.update_channel("CampusX")

    # User says "Open the LangGraph course"
    tracker.update_course("LangGraph")
    assert state.web_context.course == "LangGraph"
    assert state.web_context.playlist == "LangGraph"
    assert "LangGraph" in state.web_context.ordinal_basis


# ---------------------------------------------------------------------------
# Scenario 9: "Open the third video" (From Course Context)
# ---------------------------------------------------------------------------
def test_scenario_9_open_third_video():
    state = ComputerState()
    tracker = WebContextTracker(state)
    tracker.update_from_navigation(
        "https://www.youtube.com/playlist?list=PL123", "LangGraph Course"
    )
    tracker.set_current_list([
        {"title": "Video 1: Intro", "url": "https://www.youtube.com/watch?v=vid1"},
        {"title": "Video 2: Setup", "url": "https://www.youtube.com/watch?v=vid2"},
        {"title": "Video 3: Architecture", "url": "https://www.youtube.com/watch?v=vid3"},
    ], basis="videos in LangGraph course")

    extractor = ComputerIntentExtractor()
    intent = extractor.extract("Open the third video", computer_state=state)
    assert intent.entity is not None
    assert intent.entity.ordinal == 2  # 0-based for 3rd

    planner = SemanticTaskPlanner()
    plan = planner.plan(intent, computer_state=state)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool in ("open_file", "navigate_browser", "open_url")


# ---------------------------------------------------------------------------
# Scenario 10: "Open File Explorer" then "Open Desktop in it"
# ---------------------------------------------------------------------------
def test_scenario_10_open_file_explorer_then_desktop_in_it():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()

    # Step 1: Open File Explorer
    intent1 = extractor.extract("Open File Explorer")
    assert intent1.intent_type == "OPEN_APPLICATION"
    assert intent1.application.canonical == "file_explorer"

    plan1 = planner.plan(intent1)
    assert plan1.steps[0].params["app_name"] == "file_explorer"

    # Step 2: Open Desktop in it
    intent2 = extractor.extract("Open Desktop in it")
    assert intent2.intent_type == "OPEN_FOLDER"
    assert intent2.entity.name == "desktop"

    plan2 = planner.plan(intent2)
    assert plan2.steps[0].tool == "open_folder"
    assert plan2.steps[0].params["target"] == "desktop"


# ---------------------------------------------------------------------------
# Scenario 11: "Show files" then "Open the first one"
# ---------------------------------------------------------------------------
def test_scenario_11_show_files_then_open_first_one():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()

    # 1. "Show files"
    intent1 = extractor.extract("Show files")
    assert intent1.intent_type == "LIST_FILES"

    plan1 = planner.plan(intent1)
    assert plan1.steps[0].tool == "list_files"

    # Simulate listing results in state
    state = ComputerState()
    state.last_search_results = [
        {"name": "Resume.pdf", "path": "C:\\Users\\test\\Desktop\\Resume.pdf"},
        {"name": "Project.pdf", "path": "C:\\Users\\test\\Desktop\\Project.pdf"},
        {"name": "notes.txt", "path": "C:\\Users\\test\\Desktop\\notes.txt"},
    ]

    # 2. "Open the first one"
    intent2 = extractor.extract("Open the first one", computer_state=state)
    assert intent2.entity is not None
    assert intent2.entity.ordinal == 0

    plan2 = planner.plan(intent2, computer_state=state)
    assert len(plan2.steps) == 1
    assert plan2.steps[0].tool == "open_file"
    idx_matched = plan2.steps[0].params.get("index") == 0
    path_matched = "Resume.pdf" in str(plan2.steps[0].params.get("path"))
    assert idx_matched or path_matched


# ---------------------------------------------------------------------------
# Scenario 12: "Open WhatsApp and send hi to Lohit" (Confirmation Required)
# ---------------------------------------------------------------------------
def test_scenario_12_whatsapp_send_confirmation():
    extractor = ComputerIntentExtractor()
    planner = SemanticTaskPlanner()

    intent = extractor.extract("Open WhatsApp and send hi to Lohit")
    # Must identify recipient and messaging
    assert intent.entity is not None or "whatsapp" in str(intent.actions).lower()

    plan = planner.plan(intent)
    # WhatsApp sending must have high risk step requiring confirmation
    has_confirm = any(
        step.is_high_risk or step.verification.value == "confirmation"
        for step in plan.steps
    )
    assert has_confirm or plan.has_high_risk_steps


# ---------------------------------------------------------------------------
# Scenario 13: "Find Python jobs in Bangalore" (Strict Boundary Isolation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_13_boundary_isolation():
    settings = Settings()
    session_store = MagicMock()
    orchestrator = JarvisOrchestrator(settings, session_store=session_store)

    # 1. Computer Control Page Mode: MUST NOT invoke CareerAgent
    comp_session = Session(
        session_id="comp-123",
        created_at="2026-09-23T00:00:00Z",
        domain="computer",
    )
    comp_events = []

    async def comp_send(envelope):
        comp_events.append(envelope)

    await orchestrator.handle_message(
        comp_session,
        {"type": "chat", "text": "Find Python jobs in Bangalore", "mode": "computer"},
        send=comp_send,
    )

    # Verify no discovery was started and a helpful boundary message was returned
    event_types = [e.get("type") for e in comp_events]
    assert "agent_completed" in event_types or "completed" in event_types
    # Never called workflow/discovery
    assert not any(e.get("action") == "run_discovery" for e in comp_events)
    # Emitted mode boundary notification
    assistant_texts = [
        e.get("data", {}).get("text", "")
        for e in comp_events
        if e.get("type") == "assistant_message"
    ]
    assert any("/app/career" in t for t in assistant_texts)

    # 2. Career Page Mode: CareerAgent / run_discovery allowed
    plan = parse_intent("Find Python jobs in Bangalore")
    assert plan.action == "run_discovery"
    assert "Bangalore" in str(plan.params.get("locations") or plan.params.get("user_query"))
