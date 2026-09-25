"""Deep Consistency Test Suite for JARVIS Computer Agent.

Verifies the 14 core consistency scenarios:
1. YouTube Homepage Navigation (never search query)
2. Music Folder in Desktop (never browser search)
3. Open Desktop Resets Web Context
4. Folder Counting (no browser opened, count only)
5. Zero Fake / Synthetic Items
6. Ambiguous Command Clarification (never Google search)
7. Explicit vs Implicit Browser Resolution
8. Generation Invalidation & Stale Task Protection
9. Strict Domain Isolation (Computer vs Career)
10. Messaging Safety & Verification
11. Authoritative State Commit Model
12. Filesystem Search Routing
13. Relative Folder Path Resolution
14. Structured Debug Telemetry
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agent.task_manager import TaskLifecycle, TaskManager
from app.computer.intent_extractor import ComputerIntentExtractor
from app.computer.semantic_planner import SemanticTaskPlanner, VerificationStrategy
from app.computer.executor import ComputerAgent, HarnessDispatcher
from app.desktop.agent_harness import AgentHarness
from app.desktop.desktop_controller import DesktopController
from app.desktop.filesystem_controller import FileSystemController
from app.desktop.state import ComputerState, VerifiedState
from app.desktop.verifier import VerificationService
from app.jarvis.sessions import CareerSession, ComputerSession, InMemorySessionStore


@pytest.fixture
def clean_state():
    state = ComputerState()
    state.reset()
    return state


@pytest.fixture
def extractor():
    return ComputerIntentExtractor()


@pytest.fixture
def planner():
    return SemanticTaskPlanner()


@pytest.fixture
def verifier():
    return VerificationService()


# ---------------------------------------------------------------------------
# Scenario 1: YouTube Homepage Navigation (Never Search Query)
# ---------------------------------------------------------------------------
def test_scenario_1_youtube_homepage(extractor, planner, clean_state, verifier):
    """'Go to the homepage in YouTube' must navigate to homepage, never search."""
    intent = extractor.extract("Go to the homepage in YouTube", clean_state)
    assert intent.target_type == "SITE_HOME" or (intent.target and intent.target.lower() in ("home", "homepage"))
    assert intent.site == "youtube" or intent.destination.site == "youtube"

    plan = planner.plan(intent, clean_state)
    assert len(plan.steps) >= 1
    nav_step = [s for s in plan.steps if s.tool == "navigate_browser"][0]
    
    # Must NOT contain search_query
    assert "search_query" not in nav_step.params["url"]
    assert "youtube.com" in nav_step.params["url"]
    assert nav_step.expected_state_updates.get("web_context.page") == "home"

    # Verification must check homepage
    obs = {"browser": {"url": "https://www.youtube.com/"}}
    v_res = verifier.verify_site_home("youtube", obs)
    assert v_res.success is True
    assert v_res.evidence.get("is_home") is True

    # Negative check: URL with search query must FAIL verification
    bad_obs = {"browser": {"url": "https://www.youtube.com/results?search_query=homepageInYouTube"}}
    v_bad = verifier.verify_site_home("youtube", bad_obs)
    assert v_bad.success is False


# ---------------------------------------------------------------------------
# Scenario 2: Music Folder in Desktop (Never Browser Search)
# ---------------------------------------------------------------------------
def test_scenario_2_music_folder_in_desktop(extractor, planner, clean_state):
    """'Open music folder in the desktop' must open Desktop/Music, never Google search."""
    intent = extractor.extract("Open music folder in the desktop", clean_state)
    assert intent.intent_type in ("NAVIGATE_FILESYSTEM", "OPEN_FOLDER")
    assert intent.target.lower() == "music"
    assert intent.parent.lower() == "desktop"

    plan = planner.plan(intent, clean_state)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool == "open_folder"
    assert step.params["target"].lower() == "music"
    assert step.params["parent"].lower() == "desktop"
    assert step.verification == VerificationStrategy.FILESYSTEM_DIRECTORY


# ---------------------------------------------------------------------------
# Scenario 3: Open Desktop Resets Web Context
# ---------------------------------------------------------------------------
def test_scenario_3_open_desktop_resets_web_context(clean_state, verifier):
    """Opening Desktop/File Explorer must authoritatively clear stale web context."""
    # Stale context before
    clean_state.active_application = "Google Chrome"
    clean_state.browser_specifically_requested = "google_chrome"
    clean_state.web_context.site = "youtube"
    clean_state.web_context.page = "video"
    clean_state.web_context.video = "Deep Learning with Python"
    clean_state.web_context.current_list = [{"title": "Video 1"}]

    v_state = VerifiedState(
        task_id="t1",
        generation=1,
        is_verified=True,
        verified_app="File Explorer",
        verified_directory=str(Path.home() / "Desktop"),
        evidence={"current_directory": str(Path.home() / "Desktop"), "active_application": "File Explorer"},
    )
    clean_state.current_generation = 1
    committed = clean_state.commit_verified_state(v_state)
    assert committed is True

    # Assert web context is completely cleared
    assert clean_state.active_application == "File Explorer"
    assert "Desktop" in clean_state.current_directory
    assert clean_state.web_context.site is None
    assert clean_state.web_context.video is None
    assert clean_state.web_context.current_list == []
    assert clean_state.browser_specifically_requested is None


# ---------------------------------------------------------------------------
# Scenario 4: Folder Counting (Count Only, No Browser Opened)
# ---------------------------------------------------------------------------
def test_scenario_4_folder_counting(extractor, planner, clean_state):
    """'how many folders are present in the music folder' must plan count_directory_items."""
    intent = extractor.extract("how many folders are present in the music folder", clean_state)
    assert intent.count_only is True
    assert intent.target.lower() == "music"

    plan = planner.plan(intent, clean_state)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "count_directory_items"
    assert plan.steps[0].params["target"].lower() == "music"
    assert plan.steps[0].params["item_type"] == "folder"


# ---------------------------------------------------------------------------
# Scenario 5: Zero Fake / Synthetic Items
# ---------------------------------------------------------------------------
def test_scenario_5_zero_fake_items(clean_state):
    """Context list must contain 0 synthetic fake items."""
    from app.computer.web_context_tracker import WebContextTracker
    tracker = WebContextTracker(clean_state)
    tracker.update_from_navigation("https://www.youtube.com/results?search_query=python", "python - YouTube")
    
    # Neither web_context nor last_results should have synthetic fake video items
    assert not any(" - Video " in item.get("title", "") for item in clean_state.web_context.current_list)
    assert not any(" - Video " in item.get("title", "") for item in clean_state.last_results)


# ---------------------------------------------------------------------------
# Scenario 6: Ambiguous Command Clarification (Never Search Google)
# ---------------------------------------------------------------------------
def test_scenario_6_ambiguous_command_clarification(extractor, planner, clean_state):
    """Ambiguous command with no context must ask for clarification, never search."""
    intent = extractor.extract("open it", clean_state)
    plan = planner.plan(intent, clean_state)

    assert plan.requires_resolution is True
    assert (
        "need to know" in plan.resolution_error.lower()
        or "context" in plan.resolution_error.lower()
        or "specify" in plan.resolution_error.lower()
    )
    # Must not have any steps that search Google
    assert not any(s.tool in ("search_browser", "browser_search") for s in plan.steps)
    assert not any("google.com" in str(s.params) for s in plan.steps)


# ---------------------------------------------------------------------------
# Scenario 7: Explicit vs Implicit Browser Resolution
# ---------------------------------------------------------------------------
def test_scenario_7_explicit_vs_implicit_browser(extractor, planner, clean_state):
    """'Open YouTube in Edge' stores Edge; follow-up uses Edge."""
    intent1 = extractor.extract("Open YouTube in Edge", clean_state)
    assert intent1.explicit_browser == "microsoft_edge"

    plan1 = planner.plan(intent1, clean_state)
    clean_state.browser_specifically_requested = "microsoft_edge"
    clean_state.browser_name = "microsoft_edge"

    # Follow up
    intent2 = extractor.extract("Go to the homepage", clean_state)
    plan2 = planner.plan(intent2, clean_state)
    nav_step = [s for s in plan2.steps if s.tool == "navigate_browser"][0]
    assert nav_step.params["browser_name"] == "microsoft_edge"


# ---------------------------------------------------------------------------
# Scenario 8: Generation Invalidation & Stale Task Protection
# ---------------------------------------------------------------------------
def test_scenario_8_generation_invalidation(clean_state):
    """Stale generation commits must be rejected."""
    tm = TaskManager()
    gen1 = tm.current_generation
    task1 = tm.create_task(intent="old command", generation=gen1)

    # Invalidate by moving to next generation
    gen2 = tm.next_generation()
    clean_state.current_generation = gen2

    assert task1.is_stale() is True

    # Try committing from gen1
    v_stale = VerifiedState(
        task_id=task1.task_id,
        generation=gen1,
        is_verified=True,
        verified_app="Stale App",
    )
    committed = clean_state.commit_verified_state(v_stale)
    assert committed is False
    assert clean_state.active_application != "Stale App"


# ---------------------------------------------------------------------------
# Scenario 9: Strict Domain Isolation
# ---------------------------------------------------------------------------
def test_scenario_9_domain_isolation():
    """Computer session and Career session must be strictly isolated."""
    from app.jarvis.sessions import DomainViolation

    store = InMemorySessionStore()
    comp_session = store.get_or_create("s1", domain="computer")
    career_session = store.get_or_create("s2", domain="career")

    assert isinstance(comp_session, ComputerSession)
    assert isinstance(career_session, CareerSession)
    assert comp_session.domain == "computer"
    assert career_session.domain == "career"

    # Computer session allows computer tools, rejects career tools
    comp_session.assert_tool_allowed("open_application")
    with pytest.raises(DomainViolation):
        comp_session.assert_tool_allowed("tailor_resume")

    # Career session allows career tools, rejects computer tools
    career_session.assert_tool_allowed("tailor_resume")
    with pytest.raises(DomainViolation):
        career_session.assert_tool_allowed("open_application")


# ---------------------------------------------------------------------------
# Scenario 10: WhatsApp Messaging Safety & Verification
# ---------------------------------------------------------------------------
def test_scenario_10_messaging_safety(extractor, planner, clean_state, verifier):
    """WhatsApp messages require confirmation and verification."""
    intent = extractor.extract("send message to Alice saying hello", clean_state)
    plan = planner.plan(intent, clean_state)

    msg_step = [s for s in plan.steps if s.tool == "prepare_message"][0]
    assert msg_step.is_high_risk is True
    assert msg_step.verification == VerificationStrategy.CONFIRMATION_REQUIRED

    # Verification checks
    obs_active = {
        "active_application": "WhatsApp",
        "window": {"title": "WhatsApp - Alice", "foreground": True},
    }
    v_ok = verifier.verify_message_sent("Alice", obs_active)
    assert v_ok.success is True


# ---------------------------------------------------------------------------
# Scenario 11: Authoritative State Commit Model
# ---------------------------------------------------------------------------
def test_scenario_11_state_commit_model(clean_state):
    """State commits ONLY when is_verified=True and generation is valid."""
    clean_state.current_generation = 2

    # Unverified state must be rejected
    unverified = VerifiedState(generation=2, is_verified=False, verified_app="Unverified")
    assert clean_state.commit_verified_state(unverified) is False
    assert clean_state.active_application != "Unverified"

    # Verified state commits successfully
    verified = VerifiedState(generation=2, is_verified=True, verified_app="Verified App")
    assert clean_state.commit_verified_state(verified) is True
    assert clean_state.active_application == "Verified App"


# ---------------------------------------------------------------------------
# Scenario 12: Filesystem Search Routing
# ---------------------------------------------------------------------------
def test_scenario_12_filesystem_search_routing(extractor, planner, clean_state):
    """'search for files' must route to filesystem search, never browser."""
    intent = extractor.extract("search for resume.pdf in desktop", clean_state)
    assert intent.intent_type == "SEARCH_FILES"

    plan = planner.plan(intent, clean_state)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "search_files"
    assert "google.com" not in str(plan.steps[0].params)


# ---------------------------------------------------------------------------
# Scenario 13: Relative Folder Path Resolution
# ---------------------------------------------------------------------------
def test_scenario_13_relative_folder_path_resolution():
    """Relative paths like Desktop/Music must resolve properly."""
    dc = DesktopController()
    p = dc.resolve_folder_path("Music", parent="Desktop")
    assert "Desktop" in str(p) or "Music" in str(p)


# ---------------------------------------------------------------------------
# Scenario 14: Structured Debug Telemetry
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_14_structured_debug_telemetry(clean_state):
    """ComputerAgent execution must emit structured telemetry logs."""
    agent = ComputerAgent(state=clean_state)
    events = []
    with patch("app.computer.executor.logger.info") as mock_log:
        async for ev in agent.run("open desktop"):
            events.append(ev)

        # Check telemetry logging calls
        telemetry_calls = [
            call.args[0] for call in mock_log.call_args_list if "[TELEMETRY]" in str(call.args[0])
        ]
        assert len(telemetry_calls) >= 1


# ---------------------------------------------------------------------------
# Scenario 15: File Counting & Voice Generation Reliability
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_15_file_counting_and_generation_reliability(clean_state):
    """'how many files are available in music' must plan count_directory_items with item_type=file,
    preserve incoming voice generation, format human speech, and verify cleanly.
    """
    from app.agent.task_manager import default_task_manager

    # 1. Extractor matches 'available in'
    extractor = ComputerIntentExtractor()
    intent = extractor.extract("how many files are available in music", clean_state)
    assert intent.count_only is True
    assert intent.target.lower() == "music"
    assert intent.entity.kind == "file"

    # 2. Planner plans count_directory_items for files
    planner = SemanticTaskPlanner()
    plan = planner.plan(intent, clean_state)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "count_directory_items"
    assert plan.steps[0].params["item_type"] == "file"

    # 3. Agent execution preserves voice generation and does NOT invalidate it
    agent = ComputerAgent(state=clean_state)
    voice_gen = 1
    events = []
    async for ev in agent.run("how many files are available in music", is_voice=True, generation=voice_gen):
        events.append(ev)

    response_events = [e for e in events if e.get("agent_event_type") == "response"]
    assert len(response_events) == 1
    resp = response_events[0]
    assert "files present in the Music folder" in resp.get("text", "")
    assert resp.get("verified") is True

    # Generation 1 must remain valid in task manager (never prematurely invalidated)
    assert default_task_manager.is_generation_valid(voice_gen) is True

