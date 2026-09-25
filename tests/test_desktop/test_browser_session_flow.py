"""End-to-end multi-turn integration tests for desktop and browser session flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config.settings import Settings
from app.desktop.agent_harness import AgentHarness
from app.desktop.browser import BrowserController
from app.desktop.vault import CredentialVault
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore, Session


class RecordingBrowser(BrowserController):
    def __init__(self) -> None:
        super().__init__()
        self.navigated: list[str] = []

    def open_browser(self, url: str | None = None) -> tuple[bool, str]:
        target = url or "https://www.google.com"
        self._active_url = target
        self._history.append(target)
        self.navigated.append(target)
        return True, f"Browser opened at {target}."

    def navigate(self, url: str) -> tuple[bool, str]:
        self._active_url = url
        self._history.append(url)
        self.navigated.append(url)
        return True, f"Navigated to {url}."

    def search(self, query: str, engine: str = "google") -> tuple[bool, str]:
        from urllib.parse import quote_plus

        return self.navigate(f"https://www.google.com/search?q={quote_plus(query)}")


class EventCollector:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def send(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    @property
    def assistant_messages(self) -> list[str]:
        return [
            e["data"]["text"]
            for e in self.events
            if e.get("type") == "assistant_message" and "text" in e.get("data", {})
        ]


TestSetup = tuple[JarvisOrchestrator, Session, RecordingBrowser, CredentialVault, EventCollector]


@pytest.fixture
def test_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestSetup:
    from app.desktop.state import default_computer_state
    default_computer_state.reset()

    vault = CredentialVault(tmp_path / "credentials.json")
    browser = RecordingBrowser()
    custom_harness = AgentHarness(browser=browser, vault=vault)

    # Patch default_harness and default_vault with our test instances
    monkeypatch.setattr("app.desktop.agent_harness.default_harness", custom_harness)
    monkeypatch.setattr("app.desktop.vault.default_vault", vault)
    monkeypatch.setattr("app.desktop.web_services.default_vault", vault)

    settings = Settings(
        searchapi_api_key="",
        jarvis_assistant_llm_enabled=False,
    )
    store = InMemorySessionStore()
    session = store.get_or_create("test-session-id", domain="computer")

    collector = EventCollector()
    orch = JarvisOrchestrator(
        settings,
        session_store=store,
        graph_factory=lambda: None,
    )
    return orch, session, browser, vault, collector


class TestBrowserAndCredentialFlows:
    @pytest.mark.asyncio
    async def test_open_youtube_flow(
        self,
        test_setup: TestSetup,
    ) -> None:
        orch, session, browser, vault, collector = test_setup

        await orch.handle_message(
            session, {"type": "chat", "text": "open youtube"}, send=collector.send
        )

        assert len(browser.navigated) == 1
        # Canonical YouTube URL includes www prefix
        assert browser.navigated[0] in ("https://youtube.com", "https://www.youtube.com")
        assert session.active_browser is True
        assert any("Opening YouTube" in msg or "YouTube" in msg for msg in collector.assistant_messages)

    @pytest.mark.asyncio
    async def test_github_credential_flow(
        self,
        test_setup: TestSetup,
    ) -> None:
        orch, session, browser, vault, collector = test_setup

        # Turn 1: "open github" when no credentials exist -> asks for username
        await orch.handle_message(
            session, {"type": "chat", "text": "open github"}, send=collector.send
        )
        assert session.pending_prompt is not None
        assert session.pending_prompt["service"] == "github"
        assert any("GitHub username" in msg for msg in collector.assistant_messages)
        assert len(browser.navigated) == 0

        # Turn 2: User responds with username
        await orch.handle_message(
            session, {"type": "chat", "text": "bhanuteja-tech"}, send=collector.send
        )
        assert session.pending_prompt is None
        assert vault.get_field("github", "username") == "bhanuteja-tech"
        assert any("Saved your GitHub username" in msg for msg in collector.assistant_messages)
        assert "https://github.com/bhanuteja-tech" in browser.navigated

        # Turn 3: User says "open github" again -> directly opens profile without prompting
        browser.navigated.clear()
        collector.events.clear()
        await orch.handle_message(
            session, {"type": "chat", "text": "open github"}, send=collector.send
        )
        assert session.pending_prompt is None
        assert len(browser.navigated) == 1
        assert browser.navigated[0] in (
            "https://github.com/bhanuteja-tech", "https://github.com"
        )

    @pytest.mark.asyncio
    async def test_active_browser_chain_flow(
        self,
        test_setup: TestSetup,
    ) -> None:
        orch, session, browser, vault, collector = test_setup

        # Step 1: Open a browser
        await orch.handle_message(
            session, {"type": "chat", "text": "open a browser"}, send=collector.send
        )
        assert session.active_browser is True
        assert "https://www.google.com" in browser.navigated

        # Step 2: Open python docs in that active browser
        browser.navigated.clear()
        await orch.handle_message(
            session, {"type": "chat", "text": "open python docs"}, send=collector.send
        )
        assert len(browser.navigated) == 1
        assert "python+docs" in browser.navigated[0]

        # Step 3: Search for React tutorials
        browser.navigated.clear()
        await orch.handle_message(
            session, {"type": "chat", "text": "search for React tutorials"}, send=collector.send
        )
        assert len(browser.navigated) == 1
        assert "React+tutorials" in browser.navigated[0] or "React" in browser.navigated[0]

    @pytest.mark.asyncio
    async def test_cancel_credential_prompt(
        self,
        test_setup: TestSetup,
    ) -> None:
        orch, session, browser, vault, collector = test_setup

        # Turn 1: "open github" prompts for username
        await orch.handle_message(
            session, {"type": "chat", "text": "open github"}, send=collector.send
        )
        assert session.pending_prompt is not None

        # Turn 2: User says "never mind"
        await orch.handle_message(
            session, {"type": "chat", "text": "never mind"}, send=collector.send
        )
        assert session.pending_prompt is None
        assert any("Cancelled" in msg for msg in collector.assistant_messages)
