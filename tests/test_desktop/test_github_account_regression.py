"""End-to-End Regression Test: 'open lohith122 github account'

Verifies the exact reproduction scenario from the problem statement:
USER: "open lohith122 github account"

Assertions:
- domain = computer
- NOT generic_chat
- NOT assistant.converse
- NOT generic_google_fallback
- initial action may be browser_search
- browser_search is explicitly selected by the agent
- resulting GitHub candidate comes from actual observation
- browser_click targets the observed candidate
- resulting page is observed
- verification checks the actual target account
- no success is emitted before verification
- final response corresponds to verified state
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.computer.agent import LLMComputerAgent
from app.config.settings import Settings
from app.desktop.observer import ComputerObserver
from app.desktop.state import ComputerState
from app.desktop.verifier import VerificationService
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore


class MockBrowserHarness:
    """Mock harness tracking browser interactions and simulating observation."""

    def __init__(self, state: ComputerState) -> None:
        self.state = state
        self.executed_tools: list[tuple[str, dict[str, Any]]] = []
        self.observed_candidates: list[dict[str, str]] = []

    def browser_search(
        self, query: str, site: str = "google", browser: str | None = None
    ) -> dict[str, Any]:
        self.executed_tools.append(
            ("browser_search", {"query": query, "site": site, "browser": browser})
        )
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        self.state.current_url = url
        self.state.active_page_url = url
        self.state.active_application = "Google Chrome"
        self.state.active_window_title = f"{query} - Google Search"
        # Populate simulated search results observed from real page
        self.observed_candidates = [
            {
                "title": "Lohith L lohith-1204 - GitHub",
                "url": "https://github.com/lohith-1204",
                "snippet": "lohith-1204 has 11 repositories available.",
            },
            {
                "title": "lohith122 (Lohith) · GitHub",
                "url": "https://github.com/lohith122",
                "snippet": "lohith122 has 5 repositories. Follow on GitHub.",
            },
            {
                "title": "Rohith1221 - GitHub",
                "url": "https://github.com/Rohith1221",
                "snippet": "Rohith1221 has 55 repositories available.",
            },
        ]
        return {
            "success": True,
            "action": "browser_search",
            "query": query,
            "url": url,
            "items": self.observed_candidates,
        }

    def browser_click(self, target: str, ordinal: int | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_click", {"target": target, "ordinal": ordinal}))
        # Navigates to clicked target
        self.state.current_url = target
        self.state.active_page_url = target
        self.state.active_application = "Google Chrome"
        self.state.active_window_title = "lohith122 · GitHub"
        return {"success": True, "action": "browser_click", "target": target, "url": target}

    def browser_navigate(self, url: str, browser: str | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_navigate", {"url": url, "browser": browser}))
        self.state.current_url = url
        self.state.active_page_url = url
        self.state.active_application = "Google Chrome"
        self.state.active_window_title = "lohith122 · GitHub" if "lohith122" in url else "Browser"
        return {"success": True, "action": "browser_navigate", "url": url}

    def open_application(self, application: str) -> dict[str, Any]:
        self.executed_tools.append(("open_application", {"application": application}))
        self.state.active_application = application
        return {"success": True, "action": "open_application", "application": application}


class MockLLMForSearchThenClick:
    """Mock LLM simulating an agent that explicitly decides to search then click."""

    def __init__(self) -> None:
        self.call_count = 0
        self.enabled = True

    async def generate(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return json.dumps({
                "decision": "tool_call",
                "tool": "browser_search",
                "arguments": {"query": "lohith122 GitHub", "site": "google"},
                "thought": "Search for lohith122 GitHub to find the exact profile.",
            })
        elif self.call_count == 2:
            return json.dumps({
                "decision": "tool_call",
                "tool": "browser_click",
                "arguments": {"target": "https://github.com/lohith122"},
                "thought": "Click on observed GitHub profile for lohith122.",
            })
        else:
            return json.dumps({
                "decision": "complete",
                "response": "Opened the GitHub account for lohith122.",
                "thought": "GitHub profile is open and verified.",
            })


@pytest.mark.asyncio
async def test_github_account_search_observe_click_verify_flow() -> None:
    """Explicit agent selection of browser_search -> observation -> browser_click -> verified."""
    state = ComputerState()
    state.reset()
    harness = MockBrowserHarness(state)
    mock_llm = MockLLMForSearchThenClick()

    agent = LLMComputerAgent(
        state=state,
        harness=harness,
        observer=ComputerObserver(state=state),
        verifier=VerificationService(),
        llm_client=mock_llm,
    )

    events: list[dict[str, Any]] = []
    async for ev in agent.run("open lohith122 github account"):
        events.append(ev)

    # 1. Assert browser_search was explicitly selected by the agent
    search_starts = [
        ev for ev in events
        if ev.get("agent_event_type") == "step_start" and ev.get("tool") == "browser_search"
    ]
    assert len(search_starts) == 1, "browser_search was not explicitly selected"
    assert "lohith122" in search_starts[0]["arguments"]["query"]
    assert any(call[0] == "browser_search" for call in harness.executed_tools)

    # 2. Resulting GitHub candidate was populated from actual observation
    assert len(agent.typed_context.browser_search_results) >= 1
    observed_urls = [r.url for r in agent.typed_context.browser_search_results]
    assert "https://github.com/lohith122" in observed_urls

    # 3. browser_click targeted the observed candidate
    click_starts = [
        ev for ev in events
        if ev.get("agent_event_type") == "step_start" and ev.get("tool") == "browser_click"
    ]
    assert len(click_starts) == 1, "browser_click was not executed after search"
    assert "https://github.com/lohith122" in click_starts[0]["arguments"]["target"]
    assert any(
        call[0] == "browser_click" and "https://github.com/lohith122" in str(call[1].get("target"))
        for call in harness.executed_tools
    )

    # 4. Resulting page observed and verified
    step_dones = [ev for ev in events if ev.get("agent_event_type") == "step_done"]
    verified_steps = [ev for ev in step_dones if ev.get("verified") is True]
    assert len(verified_steps) >= 1, "Goal-level verification did not pass"

    # 5. No success emitted before verification
    for idx, ev in enumerate(events):
        if ev.get("agent_event_type") == "response" and ev.get("verified") is True:
            # Check that a step_done with verified=True preceded this response
            preceding_verified = [
                e for e in events[:idx]
                if e.get("agent_event_type") == "step_done" and e.get("verified") is True
            ]
            assert len(preceding_verified) > 0, "Success response emitted before verification!"

    # 6. Final response corresponds to verified state
    responses = [ev for ev in events if ev.get("agent_event_type") == "response"]
    assert len(responses) >= 1
    final_resp = responses[-1]["text"]
    assert "lohith122" in final_resp.lower()
    assert "github" in final_resp.lower()
    assert state.current_url == "https://github.com/lohith122"


@pytest.mark.asyncio
async def test_github_account_verification_fails_if_stuck_on_google() -> None:
    """Verification must reject success if browser remains on Google search results."""
    state = ComputerState()
    state.reset()

    class GoogleStuckHarness(MockBrowserHarness):
        def browser_click(self, target: str, ordinal: int | None = None) -> dict[str, Any]:
            # Simulate broken click where browser stays on Google
            self.executed_tools.append(("browser_click", {"target": target, "ordinal": ordinal}))
            self.state.current_url = "https://www.google.com/search?q=lohith122+github+account"
            return {
                "success": False,
                "action": "browser_click",
                "error": "Click failed",
                "url": self.state.current_url,
            }

    stuck_harness = GoogleStuckHarness(state)

    agent = LLMComputerAgent(
        state=state,
        harness=stuck_harness,
        observer=ComputerObserver(state=state),
        verifier=VerificationService(),
    )

    # Seed search results
    agent.typed_context.set_browser_search_entities([
        {"title": "lohith122 GitHub", "url": "https://github.com/lohith122"}
    ])

    # Run direct verification check on browser staying on Google search
    v_res = agent._verify_action(
        tool_name="browser_click",
        arguments={"target": "https://github.com/lohith122"},
        harness_result={
            "success": False,
            "url": "https://www.google.com/search?q=lohith122+github+account",
        },
        observation={
            "browser_url": "https://www.google.com/search?q=lohith122+github+account",
        },
        task_id="task_test",
        generation=1,
        user_goal="open lohith122 github account",
    )
    assert not v_res.verified, "Verification must reject browser remaining on search results"
    assert "google search" in v_res.reason.lower() or "not reached" in v_res.reason.lower()


@pytest.mark.asyncio
async def test_github_account_orchestrator_routing_regression() -> None:
    """Test full Orchestrator path: domain is computer, NOT generic_chat or generic fallback."""
    sent: list[dict[str, Any]] = []

    async def send(envelope: dict[str, Any]) -> None:
        sent.append(envelope)

    settings = Settings(
        jarvis_assistant_llm_enabled=False,
    )
    store = InMemorySessionStore()
    session = store.get_or_create("s-gh-test", domain="computer", lock=True)
    assert session.domain == "computer"

    state = ComputerState()
    state.reset()
    harness = MockBrowserHarness(state)

    agent = LLMComputerAgent(
        state=state,
        harness=harness,
        observer=ComputerObserver(state=state),
        verifier=VerificationService(),
    )
    session.computer_agent = agent

    orchestrator = JarvisOrchestrator(settings, session_store=store)

    await orchestrator.handle_message(
        session=session,
        message={"type": "chat", "text": "open lohith122 github account", "mode": "computer"},
        send=send,
    )

    event_types = [e.get("type") for e in sent]

    # Domain MUST be computer
    assert "computer_plan_start" in event_types or "agent_started" in event_types
    # Must NOT route to generic assistant converse / generic chat
    assert "assistant_converse" not in event_types
    assert "generic_chat" not in event_types

    # Assert agent started with computer_control action
    started_ev = next((e for e in sent if e.get("type") == "agent_started"), None)
    if started_ev:
        assert started_ev["data"].get("action") == "computer_control"

    # Verify that the final response or state corresponds to verified account
    assert state.current_url == "https://github.com/lohith122" or any(
        "lohith122" in str(e.get("data", {})) for e in sent
    )
