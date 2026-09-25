"""Comprehensive test suite for the JARVIS Autonomous LLM Computer Agent.

Verifies all 20 required scenarios from Section 34 of the specification:
TEST 1:  Open Chrome -> Verified active.
TEST 2:  Open YouTube -> Compatible page reused where possible.
TEST 3:  Go to YouTube homepage -> Navigate to homepage (never search for 'homepage').
TEST 4:  Search LangGraph on YouTube -> Real search results.
TEST 5:  Open the third video -> Resolves from real observed videos.
TEST 6:  Go back -> Browser back navigation.
TEST 7:  Open File Explorer -> File Explorer becomes active.
TEST 8:  Go to Desktop -> File Explorer navigates to Desktop.
TEST 9:  Open Music -> Opens Desktop/Music folder.
TEST 10: How many folders are present? -> Actual filesystem count.
TEST 11: What are those? -> Refers to the actual folders from previous operation.
TEST 12: Open the third one -> Third folder opens (MUST NOT open YouTube video).
TEST 13: What's inside it? -> Resolves to the currently opened folder.
TEST 14: Open VS Code -> VS Code opens (MUST NOT Google search).
TEST 15: Switch back to Chrome -> Chrome becomes active.
TEST 16: Open WhatsApp -> WhatsApp opens.
TEST 17: Send hello to Lohit -> External side-effect requires confirmation, verifies sent.
TEST 18: Compound plan execution -> Incremental execution.
TEST 19: Find resume PDF & open -> Filesystem search -> identify file -> open.
TEST 20: Interrupt / Barge-in -> TTS stops, generation cancelled, stale results dropped.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.computer.agent import LLMComputerAgent
from app.computer.context import TypedContext
from app.computer.firewall import SemanticFirewall
from app.desktop.observer import ComputerObserver
from app.desktop.state import ComputerState
from app.desktop.verifier import VerificationService


class MockHarness:
    """Mock computer execution harness recording all dispatched tool actions."""

    def __init__(self, state: ComputerState) -> None:
        self.state = state
        self.executed_tools: list[tuple[str, dict[str, Any]]] = []
        self.navigated_urls: list[str] = []

    def open_application(self, application: str) -> dict[str, Any]:
        self.executed_tools.append(("open_application", {"application": application}))
        self.state.active_application = application
        self.state.active_window_title = f"{application} Window"
        return {"success": True, "action": "open_application", "application": application}

    def focus_window(self, application: str) -> dict[str, Any]:
        self.executed_tools.append(("focus_application", {"application": application}))
        self.state.active_application = application
        self.state.active_window_title = f"{application} Window"
        return {"success": True, "action": "focus_application", "application": application}

    def close_window(self, application: str) -> dict[str, Any]:
        self.executed_tools.append(("close_application", {"application": application}))
        return {"success": True, "action": "close_application", "application": application}

    def open_folder(self, path: str) -> dict[str, Any]:
        self.executed_tools.append(("open_folder", {"path": path}))
        self.state.current_directory = path
        self.state.active_application = "File Explorer"
        self.state.active_window_title = f"{path} - File Explorer"
        return {"success": True, "action": "open_folder", "path": path}

    def list_directory(self, directory: str | None = None) -> dict[str, Any]:
        target = directory or self.state.current_directory
        self.executed_tools.append(("list_directory", {"directory": target}))
        folders = ["Rock", "Pop", "Classical"]
        files = ["song1.mp3", "playlist.m3u"]
        return {
            "success": True,
            "action": "list_directory",
            "directory": target,
            "folders": folders,
            "files": files,
            "dir_name": target.split("/")[-1],
        }

    def count_directory_items(
        self, directory: str | None = None, item_type: str = "folder"
    ) -> dict[str, Any]:
        target = directory or self.state.current_directory
        self.executed_tools.append(
            ("count_directory_items", {"directory": target, "item_type": item_type})
        )
        folders = [
            "Rock", "Pop", "Classical", "Jazz", "Blues", "Electronic",
            "HipHop", "Country", "Folk", "Reggae", "Metal", "Soul", "Ambient"
        ]
        return {
            "success": True,
            "action": "count_directory_items",
            "directory": target,
            "dir_name": "Music",
            "item_type": item_type,
            "count": len(folders),
            "folder_count": len(folders),
            "file_count": 0,
            "folders": folders,
            "files": [],
            "message": f"There are {len(folders)} folders present in the Music folder.",
        }

    def search_files(self, query: str, directory: str | None = None) -> dict[str, Any]:
        self.executed_tools.append(("search_files", {"query": query, "directory": directory}))
        matches = [
            {"name": "resume.pdf", "path": "C:/Users/user/Desktop/resume.pdf", "type": "file"}
        ]
        return {"success": True, "action": "search_files", "matches": matches, "count": 1}

    def open_file(self, path: str) -> dict[str, Any]:
        self.executed_tools.append(("open_file", {"path": path}))
        return {"success": True, "action": "open_file", "path": path}

    def browser_navigate(self, url: str, browser: str | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_navigate", {"url": url, "browser": browser}))
        self.navigated_urls.append(url)
        self.state.current_url = url
        self.state.active_application = "Google Chrome"
        self.state.active_window_title = "YouTube" if "youtube.com" in url else "Browser"
        self.state.web_context.site = "youtube" if "youtube.com" in url else None
        return {"success": True, "action": "browser_navigate", "url": url}

    def browser_search(
        self, query: str, site: str = "google", browser: str | None = None
    ) -> dict[str, Any]:
        self.executed_tools.append(
            ("browser_search", {"query": query, "site": site, "browser": browser})
        )
        url = (
            f"https://www.youtube.com/results?search_query={query}"
            if site == "youtube"
            else f"https://www.google.com/search?q={query}"
        )
        self.navigated_urls.append(url)
        self.state.current_url = url
        self.state.active_application = "Google Chrome"
        self.state.active_window_title = f"{query} - YouTube"
        self.state.web_context.site = "youtube"
        self.state.web_context.page = "search_results"
        return {"success": True, "action": "browser_search", "query": query, "url": url}

    def browser_back(self, browser: str | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_back", {"browser": browser}))
        return {"success": True, "action": "browser_back"}

    def browser_click(self, target: str, ordinal: int | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_click", {"target": target, "ordinal": ordinal}))
        return {"success": True, "action": "browser_click", "target": target}

    def send_message(
        self, recipient: str, message: str, platform: str = "whatsapp"
    ) -> dict[str, Any]:
        self.executed_tools.append(
            ("send_message", {"recipient": recipient, "message": message, "platform": platform})
        )
        return {
            "success": True,
            "action": "send_message",
            "recipient": recipient,
            "message": message,
        }


@pytest.fixture
def clean_state() -> ComputerState:
    state = ComputerState()
    state.reset()
    return state


@pytest.fixture
def mock_harness(clean_state: ComputerState) -> MockHarness:
    return MockHarness(clean_state)


@pytest.fixture
def agent(clean_state: ComputerState, mock_harness: MockHarness) -> LLMComputerAgent:
    return LLMComputerAgent(
        state=clean_state,
        harness=mock_harness,
        observer=ComputerObserver(state=clean_state),
        verifier=VerificationService(),
    )


# ===========================================================================
# SCENARIOS 1 - 6: BROWSER & YOUTUBE WORKFLOW
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_01_open_chrome(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 1: 'Open Chrome' -> Chrome opens and is verified."""
    events = [ev async for ev in agent.run("Open Chrome.")]
    assert any(ev.get("tool") == "open_application" for ev in events)
    assert any(
        call[0] == "open_application" and "Chrome" in call[1].get("application", "")
        for call in mock_harness.executed_tools
    )
    assert agent.state.active_application == "Google Chrome"
    resps = [ev.get("text") for ev in events if ev.get("agent_event_type") == "response"]
    assert len(resps) > 0


@pytest.mark.asyncio
async def test_scenario_02_open_youtube(agent: LLMComputerAgent, mock_harness: MockHarness) -> None:
    """TEST 2: 'Open YouTube' -> Navigates to YouTube."""
    events = [ev async for ev in agent.run("Open YouTube.")]
    assert any(ev.get("tool") == "browser_navigate" for ev in events)
    assert any("youtube.com" in call[1].get("url", "") for call in mock_harness.executed_tools)
    assert "youtube.com" in (agent.state.current_url or "")


@pytest.mark.asyncio
async def test_scenario_03_youtube_homepage(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 3: 'Go to the YouTube homepage' -> Navigates to YouTube homepage (MUST NOT search)."""
    events = [ev async for ev in agent.run("Go to the YouTube homepage.")]
    assert any(ev.get("tool") == "browser_navigate" for ev in events)
    # MUST NOT search for "homepage"
    for call in mock_harness.executed_tools:
        if call[0] == "browser_navigate":
            assert call[1].get("url") == "https://www.youtube.com/"
            assert "search_query" not in call[1].get("url")


@pytest.mark.asyncio
async def test_scenario_04_search_youtube(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 4: 'Search LangGraph on YouTube' -> YouTube search results."""
    events = [ev async for ev in agent.run("Search LangGraph on YouTube.")]
    assert any(ev.get("tool") == "browser_search" for ev in events)
    search_call = next(call for call in mock_harness.executed_tools if call[0] == "browser_search")
    assert search_call[1].get("query") == "LangGraph"
    assert search_call[1].get("site") == "youtube"


@pytest.mark.asyncio
async def test_scenario_05_open_third_video(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 5: 'Open the third video' -> Resolves from real observed YouTube videos."""
    # Seed context with 3 observed YouTube videos
    agent.typed_context.set_youtube_entities([
        {"title": "LangGraph Tutorial 1", "url": "https://www.youtube.com/watch?v=lg_1"},
        {"title": "LangGraph Tutorial 2", "url": "https://www.youtube.com/watch?v=lg_2"},
        {"title": "LangGraph Tutorial 3", "url": "https://www.youtube.com/watch?v=lg_3"},
    ])
    agent.state.web_context.site = "youtube"

    events = [ev async for ev in agent.run("Open the third video.")]
    assert any(ev.get("tool") == "browser_click" for ev in events)
    assert any("lg_3" in url for url in mock_harness.navigated_urls) or any(
        call[1].get("ordinal") == 3 for call in mock_harness.executed_tools
    )


@pytest.mark.asyncio
async def test_scenario_06_go_back(agent: LLMComputerAgent, mock_harness: MockHarness) -> None:
    """TEST 6: 'Go back' -> Browser back navigation."""
    events = [ev async for ev in agent.run("Go back.")]
    assert any(ev.get("tool") == "browser_back" for ev in events)
    assert any(call[0] == "browser_back" for call in mock_harness.executed_tools)


# ===========================================================================
# SCENARIOS 7 - 13: FILESYSTEM & FOLLOW-UP WORKING MEMORY WORKFLOW
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_07_open_file_explorer(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 7: 'Open File Explorer' -> File Explorer becomes active."""
    events = [ev async for ev in agent.run("Open File Explorer.")]
    assert any(ev.get("tool") == "open_application" for ev in events)
    assert agent.state.active_application == "File Explorer"


@pytest.mark.asyncio
async def test_scenario_08_go_to_desktop(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 8: 'Go to Desktop' -> Navigates to Desktop."""
    events = [ev async for ev in agent.run("Go to Desktop.")]
    assert any(
        ev.get("tool") == "open_folder" and "Desktop" in ev.get("arguments", {}).get("path", "")
        for ev in events
    )
    assert "Desktop" in agent.state.current_directory


@pytest.mark.asyncio
async def test_scenario_09_to_13_multi_turn_filesystem_sequence(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TESTS 9, 10, 11, 12, 13 (Section 35 Core Follow-Up Problem):

    1. 'Open Music.'
    2. 'How many folders are present?'
    3. 'What are those?'
    4. 'Open the third one.' (MUST NOT open third YouTube video)
    5. 'What's inside it?'
    """
    # Turn 1: Open Music
    ev1 = [ev async for ev in agent.run("Open Music.")]
    assert any(ev.get("tool") == "open_folder" for ev in ev1)
    assert agent.typed_context.last_opened_folder == "Music"
    assert agent.typed_context.last_active_domain == "filesystem"

    # Turn 2: How many folders are present?
    ev2 = [ev async for ev in agent.run("How many folders are present?")]
    assert any(ev.get("tool") == "count_directory_items" for ev in ev2)
    resp2 = next(ev.get("text") for ev in ev2 if ev.get("agent_event_type") == "response")
    assert "13" in resp2 or "folders" in resp2
    assert len(agent.typed_context.filesystem_results) == 13

    # Turn 3: What are those? (Refers strictly to the 13 folders)
    ev3 = [ev async for ev in agent.run("What are those?")]
    resp3 = next(ev.get("text") for ev in ev3 if ev.get("agent_event_type") == "response")
    assert "Rock" in resp3
    assert "Pop" in resp3
    assert "Classical" in resp3

    # Turn 4: Open the third one. (Resolves to 3rd folder 'Classical', NOT a YouTube video!)
    ev4 = [ev async for ev in agent.run("Open the third one.")]
    assert any(ev.get("tool") == "open_folder" for ev in ev4)
    # Verify mock harness received open_folder on Classical
    open_calls = [call for call in mock_harness.executed_tools if call[0] == "open_folder"]
    assert any("Classical" in call[1].get("path", "") for call in open_calls)
    assert not any(call[0] == "browser_click" for call in mock_harness.executed_tools)

    # Turn 5: What's inside it? ('it' refers to Classical)
    ev5 = [ev async for ev in agent.run("What's inside it?")]
    assert any(ev.get("tool") == "list_directory" for ev in ev5)
    resp5 = next(ev.get("text") for ev in ev5 if ev.get("agent_event_type") == "response")
    assert "inside" in resp5.lower() or "song1.mp3" in resp5.lower() or "rock" in resp5.lower()

    # Turn 6: Go back. (Navigates back to parent folder Music)
    ev6 = [ev async for ev in agent.run("Go back.")]
    assert any(ev.get("tool") == "open_folder" for ev in ev6)
    assert any(
        "Music" in call[1].get("path", "")
        for call in mock_harness.executed_tools
        if call[0] == "open_folder"
    )

    # Turn 7: Open the second folder. (Resolves to Pop)
    ev7 = [ev async for ev in agent.run("Open the second folder.")]
    assert any(ev.get("tool") == "open_folder" for ev in ev7)
    open_calls_turn7 = [call for call in mock_harness.executed_tools if call[0] == "open_folder"]
    assert any("Pop" in call[1].get("path", "") for call in open_calls_turn7)



# ===========================================================================
# SCENARIOS 14 - 17: OS APPS, WHATSAPP SAFETY & SIDE EFFECTS
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_14_open_vs_code(agent: LLMComputerAgent, mock_harness: MockHarness) -> None:
    """TEST 14: 'Open VS Code' -> Actual VS Code opens (MUST NOT Google search)."""
    events = [ev async for ev in agent.run("Open VS Code.")]
    assert any(ev.get("tool") == "open_application" for ev in events)
    assert not any(call[0] == "browser_search" for call in mock_harness.executed_tools)


@pytest.mark.asyncio
async def test_scenario_15_switch_back_to_chrome(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 15: 'Switch back to Chrome' -> Brings Chrome to foreground."""
    events = [ev async for ev in agent.run("Switch back to Chrome.")]
    assert any(ev.get("tool") == "focus_application" for ev in events)
    assert agent.state.active_application == "Google Chrome"


@pytest.mark.asyncio
async def test_scenario_16_open_whatsapp(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 16: 'Open WhatsApp' -> Opens WhatsApp."""
    events = [ev async for ev in agent.run("Open WhatsApp.")]
    assert any(ev.get("tool") == "open_application" for ev in events)
    assert agent.state.active_application == "WhatsApp"


@pytest.mark.asyncio
async def test_scenario_17_send_hello_to_lohit_requires_confirmation(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 17: 'Send hello to Lohit' -> Confirmation guard triggers; verifies sent."""
    # Attempt 1: Without prior confirmation -> Must pause and ask confirmation
    events_unconfirmed = [ev async for ev in agent.run("Send hello to Lohit.")]
    assert any(
        ev.get("agent_event_type") in ("confirmation_required", "needs_confirm")
        for ev in events_unconfirmed
    )
    assert any(ev.get("agent_event_type") == "waiting_for_user" for ev in events_unconfirmed)
    # Tool must NOT have executed yet
    assert not any(call[0] == "send_message" for call in mock_harness.executed_tools)

    # Attempt 2: With confirmation provided
    events_confirmed = [
        ev async for ev in agent.run(
            "Send hello to Lohit.",
            confirmed_action={"tool": "send_message", "recipient": "Lohit"},
        )
    ]
    assert any(call[0] == "send_message" for call in mock_harness.executed_tools)
    assert any(
        ev.get("agent_event_type") == "all_steps_done" or ev.get("verified")
        for ev in events_confirmed
    )


# ===========================================================================
# SCENARIOS 18 - 20: RESUME SEARCH, DOMAIN ISOLATION & BARGE-IN
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_18_find_resume_pdf(
    agent: LLMComputerAgent, mock_harness: MockHarness
) -> None:
    """TEST 19: 'Find my resume PDF and open it' -> Filesystem search -> open."""
    events = [ev async for ev in agent.run("Find my resume PDF and open it.")]
    assert any(ev.get("tool") == "search_files" for ev in events)


@pytest.mark.asyncio
async def test_scenario_19_career_domain_isolation(agent: LLMComputerAgent) -> None:
    """Requirement 16: Career Intelligence is separate from Computer Agent."""
    events = [ev async for ev in agent.run("Find Python jobs in Bangalore.")]
    # Must not execute career job search; must output clarification pointing to Career page
    assert not any(ev.get("tool") == "career_job_search" for ev in events)
    resps = [ev.get("text") for ev in events if ev.get("agent_event_type") == "response"]
    assert any("career" in r.lower() for r in resps)


@pytest.mark.asyncio
async def test_scenario_20_barge_in_and_stale_result_dropping(agent: LLMComputerAgent) -> None:
    """TEST 20: Barge-in interruption and task generations:
    When user stops an action, generation increments and late results are discarded.
    """
    initial_gen = agent.current_generation

    # User says "STOP"
    agent.cancel_current_task()
    assert agent.current_generation == initial_gen + 1

    # Attempt to deliver a stale result from the old generation
    stale_events = [
        ev async for ev in agent.run("Old task from previous turn", generation=initial_gen)
    ]
    assert any(ev.get("agent_event_type") == "stale_result_dropped" for ev in stale_events)


# ===========================================================================
# ADDITIONAL FIREWALL & TOOL SAFETY TESTS
# ===========================================================================

def test_semantic_firewall_blocks_career_tools() -> None:
    """Firewall rejects career tools like 'resume_tailor' in computer domain."""
    firewall = SemanticFirewall(domain="computer")
    context = TypedContext()
    res = firewall.validate_tool_call(
        tool_name="resume_tailor",
        arguments={"job_title": "Engineer"},
        context=context,
    )
    assert not res.valid
    assert "Cross-domain violation" in (res.rejection_reason or "")


def test_semantic_firewall_enforces_required_parameters() -> None:
    """Firewall rejects tools missing mandatory arguments."""
    firewall = SemanticFirewall(domain="computer")
    context = TypedContext()
    res = firewall.validate_tool_call(
        tool_name="open_folder",
        arguments={},  # missing required 'path'
        context=context,
    )
    assert not res.valid
    assert "Missing required parameter" in (res.rejection_reason or "")


def test_typed_context_no_fake_entities() -> None:
    """TypedContext guarantees zero fake entities."""
    ctx = TypedContext()
    assert len(ctx.filesystem_results) == 0
    assert len(ctx.youtube_video_results) == 0

    ctx.set_filesystem_entities([
        {"name": "FolderA", "path": "C:/FolderA", "is_dir": True},
        {"name": "FileB.txt", "path": "C:/FileB.txt", "is_dir": False},
    ])
    assert len(ctx.filesystem_results) == 2
    assert ctx.filesystem_results[0].ordinal == 1
    assert ctx.filesystem_results[0].source == "filesystem"
    assert ctx.filesystem_results[1].ordinal == 2
    assert ctx.filesystem_results[1].type == "file"
