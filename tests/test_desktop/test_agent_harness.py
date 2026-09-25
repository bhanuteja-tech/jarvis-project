"""Unit tests for AgentHarness."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.desktop.actions import DesktopAction
from app.desktop.agent_harness import AgentHarness
from app.desktop.browser import BrowserController
from app.desktop.vault import CredentialVault
from app.jarvis.sessions import Session


class FakeBrowser(BrowserController):
    def __init__(self) -> None:
        super().__init__()
        self.opened_urls: list[str] = []
        self.searched_queries: list[str] = []

    def open_browser(self, url: str | None = None) -> tuple[bool, str]:
        target = url or "https://www.google.com"
        self._active_url = target
        self._history.append(target)
        self.opened_urls.append(target)
        return True, f"Browser opened at {target}."

    def navigate(self, url: str) -> tuple[bool, str]:
        self._active_url = url
        self._history.append(url)
        self.opened_urls.append(url)
        return True, f"Navigated to {url}."

    def search(self, query: str, engine: str = "google") -> tuple[bool, str]:
        self.searched_queries.append(query)
        return self.navigate(f"https://www.google.com/search?q={query}")


@pytest.fixture
def harness(tmp_path: Path) -> tuple[AgentHarness, FakeBrowser, CredentialVault]:
    vault = CredentialVault(tmp_path / "credentials.json")
    browser = FakeBrowser()
    harness = AgentHarness(browser=browser, vault=vault)
    return harness, browser, vault


class TestAgentHarness:
    def test_open_browser_sets_session_active(
        self, harness: tuple[AgentHarness, FakeBrowser, CredentialVault]
    ) -> None:
        agent_harness, browser, _ = harness
        session = Session("sess-1", "2026-09-22T00:00:00Z")
        assert session.active_browser is False

        res = agent_harness.execute_command(DesktopAction.OPEN_BROWSER, {}, session=session)
        assert res.success is True
        assert session.active_browser is True
        assert "https://www.google.com" in browser.opened_urls

    def test_search_web_navigates_browser(
        self, harness: tuple[AgentHarness, FakeBrowser, CredentialVault]
    ) -> None:
        agent_harness, browser, _ = harness
        session = Session("sess-1", "2026-09-22T00:00:00Z")
        res = agent_harness.execute_command(
            DesktopAction.SEARCH_WEB, {"query": "React tutorials"}, session=session
        )
        assert res.success is True
        assert session.active_browser is True
        assert "React tutorials" in browser.searched_queries

    def test_open_youtube_service(
        self, harness: tuple[AgentHarness, FakeBrowser, CredentialVault]
    ) -> None:
        agent_harness, browser, _ = harness
        session = Session("sess-1", "2026-09-22T00:00:00Z")
        res = agent_harness.execute_command(
            DesktopAction.OPEN_SERVICE, {"service": "youtube", "account": False}, session=session
        )
        assert res.success is True
        assert session.active_browser is True
        assert "https://youtube.com" in browser.opened_urls

    def test_open_github_account_without_credential_triggers_prompt(
        self, harness: tuple[AgentHarness, FakeBrowser, CredentialVault]
    ) -> None:
        agent_harness, browser, vault = harness
        session = Session("sess-1", "2026-09-22T00:00:00Z")
        res = agent_harness.execute_command(
            DesktopAction.OPEN_SERVICE, {"service": "github", "account": True}, session=session
        )
        assert res.success is True
        assert res.needs_user_input is True
        assert res.action == "await_credential"
        assert session.pending_prompt is not None
        assert session.pending_prompt["service"] == "github"
        assert len(browser.opened_urls) == 0

    def test_handle_credential_response_saves_and_opens_account(
        self, harness: tuple[AgentHarness, FakeBrowser, CredentialVault]
    ) -> None:
        agent_harness, browser, vault = harness
        session = Session("sess-1", "2026-09-22T00:00:00Z")
        session.pending_prompt = {
            "type": "await_credential",
            "service": "github",
            "field": "username",
            "target_action": "open_service",
            "account": True,
        }

        res = agent_harness.handle_credential_response(
            "bhanuteja-tech", session.pending_prompt, session=session
        )
        assert res.success is True
        assert session.pending_prompt is None
        assert vault.get_field("github", "username") == "bhanuteja-tech"
        assert "https://github.com/bhanuteja-tech" in browser.opened_urls
        assert session.active_browser is True

    @pytest.mark.parametrize(
        "input_text,expected_handle",
        [
            ("bhanuteja-tech", "bhanuteja-tech"),
            ("my username is bhanuteja-tech", "bhanuteja-tech"),
            ("it's bhanuteja-tech", "bhanuteja-tech"),
            ("@bhanuteja-tech", "bhanuteja-tech"),
            ("username: bhanuteja-tech", "bhanuteja-tech"),
            ("use bhanuteja-tech", "bhanuteja-tech"),
        ],
    )
    def test_extract_credential_variations(
        self,
        harness: tuple[AgentHarness, FakeBrowser, CredentialVault],
        input_text: str,
        expected_handle: str,
    ) -> None:
        agent_harness, browser, vault = harness
        extracted = agent_harness._extract_credential_value(input_text, "username")
        assert extracted == expected_handle
