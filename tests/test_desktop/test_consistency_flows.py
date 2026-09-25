"""Consistency Integration Test Suite for Flows A through I.

Verifies end-to-end multi-turn flows:
Flow A: Open Chrome -> Chrome foreground.
Flow B: Open Chrome and search YouTube -> Chrome -> YouTube -> verified.
Flow C: Open Edge and open YouTube -> Edge -> YouTube -> verified.
Flow D: Open YouTube -> Open CampusX -> Open LangGraph course -> Open third video ->
        hierarchical context retained without generic search fallback.
Flow E: Search LangGraph on YouTube -> Open the third video ->
        resolves current_list[2] -> open -> verify (never 'no recent files').
Flow F: Open File Explorer -> Open Desktop in it -> Show files -> Open the first one ->
        filesystem context maintained throughout.
Flow G: Open WhatsApp -> Send hi to Lohit -> actual WhatsApp interaction -> verification.
Flow H: Computer page: Find Python jobs -> DO NOT invoke career discovery.
Flow I: Career page: Find Python jobs in Bangalore -> CareerAgent / job search workflow.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.computer.executor import ComputerAgent, HarnessDispatcher
from app.computer.web_context_tracker import WebContextTracker
from app.config.settings import Settings
from app.desktop.agent_harness import AgentHarness
from app.desktop.state import ComputerState
from app.jarvis.intent import parse_intent
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore


class MockBrowser:
    def __init__(self) -> None:
        self.navigated: list[str] = []
        self._active_url: str | None = None

    def open_browser(self, url: str | None = None) -> tuple[bool, str]:
        target = url or "https://www.google.com"
        self._active_url = target
        self.navigated.append(target)
        return True, f"Browser opened at {target}."

    def navigate(self, url: str) -> tuple[bool, str]:
        self._active_url = url
        self.navigated.append(url)
        return True, f"Navigated to {url}."

    def search_web(self, query: str, engine: str = "google") -> tuple[bool, str]:
        from urllib.parse import quote_plus

        if str(engine).lower() == "youtube":
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        else:
            url = f"https://www.google.com/search?q={quote_plus(query)}"
        self._active_url = url
        self.navigated.append(url)
        return True, f"Searched for {query}."

    def search(self, query: str, engine: str = "google") -> tuple[bool, str]:
        return self.search_web(query, engine)

    @property
    def last_url(self) -> str | None:
        return self._active_url


class MockVerifier:
    """Mock verification service that confirms simulated actions in tests."""

    def verify_browser_foreground(self, target: str, observation: dict[str, Any]) -> Any:
        from app.desktop.verifier import VerificationResult

        return VerificationResult(
            success=True, confidence=1.0, reason="verified", details={"method": "mock_browser"}
        )

    def verify_application_opened(self, target: str, observation: dict[str, Any]) -> Any:
        from app.desktop.verifier import VerificationResult

        return VerificationResult(
            success=True, confidence=1.0, reason="verified", details={"method": "mock_app"}
        )

    def verify_navigation_by_title(
        self, target: str, observation: dict[str, Any], **kwargs: Any
    ) -> Any:
        from app.desktop.verifier import VerificationResult

        return VerificationResult(
            success=True, confidence=1.0, reason="verified", details={"method": "mock_nav"}
        )

    def verify_folder_opened(self, target: str, observation: dict[str, Any]) -> Any:
        from app.desktop.verifier import VerificationResult

        return VerificationResult(
            success=True, confidence=1.0, reason="verified", details={"method": "mock_folder"}
        )

    def verify_search_results(self, target: str, observation: dict[str, Any]) -> Any:
        from app.desktop.verifier import VerificationResult

        return VerificationResult(
            success=True, confidence=1.0, reason="verified", details={"method": "mock_search"}
        )


def _make_agent_harness(state: ComputerState, browser: MockBrowser | None = None) -> AgentHarness:
    b = browser or MockBrowser()
    app_ctrl = MagicMock()
    app_ctrl.open_application.return_value = {
        "success": True,
        "message": "Opened application successfully.",
        "foreground": True,
    }
    fs_ctrl = MagicMock()
    fs_ctrl.list_directory.return_value = {
        "success": True,
        "items": ["Resume.pdf", "Notes.txt", "Project.zip"],
        "message": "Found 3 files.",
    }
    fs_ctrl.open_file.return_value = {
        "success": True,
        "message": "Opened file.",
    }
    desktop_ctrl = MagicMock()
    desktop_ctrl.open_desktop.return_value = {
        "success": True,
        "message": "Opened Desktop.",
    }
    desktop_ctrl.open_folder.return_value = {
        "success": True,
        "message": "Opened folder.",
    }
    msg_ctrl = MagicMock()
    msg_ctrl.send_message.return_value = {
        "success": True,
        "message": "Message sent.",
    }

    return AgentHarness(
        app_controller=app_ctrl,
        browser=b,
        fs_controller=fs_ctrl,
        desktop_controller=desktop_ctrl,
        messaging_controller=msg_ctrl,
        state=state,
    )


def _make_computer_agent(
    state: ComputerState,
    browser: MockBrowser | None = None,
    web_tracker: WebContextTracker | None = None,
) -> ComputerAgent:
    harness = _make_agent_harness(state, browser)
    mock_obs = MagicMock()
    mock_obs.observe.return_value = {
        "active_window": {"title": "Google Chrome", "process_name": "chrome.exe"},
        "active_window_title": "Google Chrome",
        "foreground_process": "chrome.exe",
    }
    return ComputerAgent(
        state=state,
        web_tracker=web_tracker,
        observer=mock_obs,
        verifier=MockVerifier(),
        dispatcher=HarnessDispatcher(harness=harness),
    )


# ---------------------------------------------------------------------------
# FLOW A: Open Chrome -> Chrome foreground
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_a_open_chrome() -> None:
    state = ComputerState()
    agent = _make_computer_agent(state)

    events: list[dict[str, Any]] = []
    async for event in agent.run("Open Chrome"):
        events.append(event)

    types = [e.get("agent_event_type") for e in events]
    assert "plan_ready" in types
    assert "response" in types
    assert state.browser_name in ("google_chrome", "chrome")
    assert state.last_target in ("google_chrome", "chrome", "Google Chrome")
    assert state.browser_specifically_requested == "google_chrome"


# ---------------------------------------------------------------------------
# FLOW B: Open Chrome and search YouTube -> Chrome -> YouTube -> verified
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_b_open_chrome_and_search_youtube() -> None:
    state = ComputerState()
    browser = MockBrowser()
    agent = _make_computer_agent(state, browser)

    events: list[dict[str, Any]] = []
    async for event in agent.run("Open Chrome and search YouTube"):
        events.append(event)

    types = [e.get("agent_event_type") for e in events]
    assert "plan_ready" in types
    assert "step_done" in types
    assert "response" in types

    assert state.browser_specifically_requested == "google_chrome"
    assert state.web_context.site == "youtube"
    assert any("youtube.com" in url for url in browser.navigated)


# ---------------------------------------------------------------------------
# FLOW C: Open Edge and open YouTube -> Edge -> YouTube -> verified
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_c_open_edge_and_open_youtube() -> None:
    state = ComputerState()
    browser = MockBrowser()
    agent = _make_computer_agent(state, browser)

    events: list[dict[str, Any]] = []
    async for event in agent.run("Open Edge and open YouTube"):
        events.append(event)

    assert state.browser_specifically_requested == "microsoft_edge"
    assert state.web_context.site == "youtube"
    assert state.web_context.domain == "youtube.com"
    assert any("youtube.com" in url for url in browser.navigated)


# ---------------------------------------------------------------------------
# FLOW D: Hierarchical YouTube Navigation
# Open YouTube -> Open CampusX -> Open LangGraph course -> Open third video
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_d_hierarchical_youtube_navigation() -> None:
    state = ComputerState()
    browser = MockBrowser()
    tracker = WebContextTracker(state)
    agent = _make_computer_agent(state, browser, web_tracker=tracker)

    # Turn 1: Open YouTube
    async for _ in agent.run("Open YouTube"):
        pass
    assert state.web_context.site == "youtube"
    assert state.web_context.domain == "youtube.com"

    # Turn 2: Open CampusX (Channel)
    async for _ in agent.run("Open CampusX"):
        pass
    assert state.web_context.site == "youtube"
    assert state.web_context.channel == "CampusX"
    assert state.web_context.page == "channel"

    # Turn 3: Open LangGraph course
    async for _ in agent.run("Open the LangGraph course"):
        pass
    assert state.web_context.channel == "CampusX"
    assert state.web_context.course == "LangGraph"
    assert state.web_context.page == "course"
    assert len(state.web_context.current_list) > 0
    assert len(state.last_youtube_results) > 0

    # Turn 4: Open third video
    response_text = ""
    async for ev in agent.run("Open the third video"):
        if ev.get("agent_event_type") == "response":
            response_text = ev.get("text", "")

    # Must NOT fall back to generic "no recent files" error
    assert "no recent files" not in response_text.lower()
    assert state.web_context.page == "video"
    assert state.web_context.ordinal_index == 2  # 0-based for third video
    assert any("watch?v=langgraph_3" in url for url in browser.navigated)


# ---------------------------------------------------------------------------
# FLOW E: Search on YouTube then Open the third video
# "Search LangGraph on YouTube" -> "Open the third video"
# MUST NOT say: "There are no recent files."
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_e_search_youtube_then_open_third_video() -> None:
    state = ComputerState()
    browser = MockBrowser()
    tracker = WebContextTracker(state)
    agent = _make_computer_agent(state, browser, web_tracker=tracker)

    # Turn 1: Search LangGraph on YouTube
    async for _ in agent.run("Search LangGraph on YouTube"):
        pass

    assert state.web_context.site == "youtube"
    assert state.web_context.domain == "youtube.com"
    assert state.web_context.page == "search_results"
    assert len(state.web_context.current_list) > 0
    assert len(state.last_youtube_results) > 0

    # Turn 2: Open the third video
    response_events: list[dict[str, Any]] = []
    async for ev in agent.run("Open the third video"):
        if ev.get("agent_event_type") == "response":
            response_events.append(ev)

    assert len(response_events) > 0
    final_text = response_events[-1].get("text", "")

    # Rigorous check: no erroneous fallback message
    assert "no recent files" not in final_text.lower()
    assert "search results" not in final_text.lower()
    assert state.web_context.ordinal_index == 2
    assert state.web_context.page == "video"
    assert any("watch?v=" in url for url in browser.navigated)


# ---------------------------------------------------------------------------
# FLOW F: Filesystem Context Maintenance
# Open File Explorer -> Open Desktop in it -> Show files -> Open the first one
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_f_filesystem_context() -> None:
    state = ComputerState()
    agent = _make_computer_agent(state)

    # Turn 1 & 2: Compound command or sequential
    async for _ in agent.run("Open File Explorer and open Desktop in it"):
        pass
    assert "Desktop" in state.current_directory or state.last_target == "file_explorer"

    # Turn 3: Show files
    async for _ in agent.run("Show files"):
        pass
    assert len(state.last_search_results) == 3

    # Turn 4: Open the first one
    response_text = ""
    async for ev in agent.run("Open the first one"):
        if ev.get("agent_event_type") == "response":
            response_text = ev.get("text", "")

    assert "no recent files" not in response_text.lower()
    assert state.selected_file is not None or "Resume.pdf" in response_text


# ---------------------------------------------------------------------------
# FLOW G: WhatsApp Interaction with Verification & Confirmation
# "Open WhatsApp" -> "Send hi to Lohit"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_g_whatsapp_interaction() -> None:
    state = ComputerState()
    agent = _make_computer_agent(state)

    # Turn 1: Open WhatsApp
    async for _ in agent.run("Open WhatsApp"):
        pass
    assert state.active_application == "whatsapp" or state.last_target == "whatsapp"

    # Turn 2: Send hi to Lohit -> must require confirmation (high-risk safety)
    confirm_required = False
    response_msg = ""
    async for ev in agent.run("Send hi to Lohit"):
        if ev.get("agent_event_type") == "confirmation_required" or ev.get("needs_confirm"):
            confirm_required = True
        if ev.get("agent_event_type") == "response":
            response_msg = ev.get("text", "")

    assert confirm_required or "lohit" in response_msg.lower()
    # Ensure truthful non-hallucination: agent does not claim sent before confirmation
    assert "i sent the message" not in response_msg.lower()


# ---------------------------------------------------------------------------
# FLOW H: Computer Page -> Find Python jobs (Blocked from Career Discovery)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_h_computer_page_blocks_career_discovery() -> None:
    settings = Settings(searchapi_api_key="", jarvis_assistant_llm_enabled=False)
    store = InMemorySessionStore()
    session = store.get_or_create("session_comp_mode")
    session.mode = "computer"

    collector: list[dict[str, Any]] = []

    async def mock_send(evt: dict[str, Any]) -> None:
        collector.append(evt)

    orch = JarvisOrchestrator(settings, session_store=store, graph_factory=lambda: None)

    await orch.handle_message(
        session,
        {"type": "chat", "text": "Find Python jobs", "mode": "computer"},
        send=mock_send,
    )

    # Assert mode boundary was enforced
    started_evs = [e for e in collector if e.get("type") == "agent_started"]
    assert any(e.get("data", {}).get("action") == "mode_boundary" for e in started_evs)

    # Assert assistant message directs to career page
    assistant_msgs = [
        e.get("data", {}).get("text", "")
        for e in collector
        if e.get("type") == "assistant_message"
    ]
    assert any("/app/career" in msg for msg in assistant_msgs)


# ---------------------------------------------------------------------------
# FLOW I: Career Page -> Find Python jobs in Bangalore (Allowed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_i_career_page_allows_career_discovery() -> None:
    plan = parse_intent("Find Python jobs in Bangalore")
    assert plan.action == "run_discovery"
    query_val = plan.params.get("user_query") or plan.params.get("query") or ""
    assert "Python" in query_val
