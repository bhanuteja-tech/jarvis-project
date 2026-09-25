"""Tests for the desktop command parser (deterministic regex patterns)."""

from __future__ import annotations

import pytest

from app.desktop.actions import DesktopAction
from app.desktop.parser import parse_desktop_command


class TestOpenApp:
    """Parser: open/launch/start app commands."""

    @pytest.mark.parametrize(
        "cmd,expected_app",
        [
            ("open chrome", "chrome"),
            ("launch notepad", "notepad"),
            ("start calculator", "calculator"),
            ("run vscode", "vscode"),
            ("open visual studio code", "visual studio code"),
            ("Open Chrome", "chrome"),
            ("LAUNCH NOTEPAD", "notepad"),
            ("open file explorer", "file explorer"),
            ("open discord", "discord"),
            ("start spotify", "spotify"),
        ],
    )
    def test_open_known_app(self, cmd: str, expected_app: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.OPEN_APP
        assert params["app_name"] == expected_app

    @pytest.mark.parametrize(
        "cmd",
        [
            "open randomnonexistentapp123",
            "launch xyzzzz",
            "open my heart",
        ],
    )
    def test_open_unknown_app_returns_none(self, cmd: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is None


class TestOpenUrl:
    """Parser: URL opening commands."""

    @pytest.mark.parametrize(
        "cmd,expected_url",
        [
            ("open github.com", "github.com"),
            ("go to youtube.com", "youtube.com"),
            ("visit google.com", "google.com"),
            ("navigate to example.com/path", "example.com/path"),
            ("open https://www.google.com", "https://www.google.com"),
        ],
    )
    def test_open_url(self, cmd: str, expected_url: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.OPEN_URL
        assert params["url"] == expected_url


class TestSearchWeb:
    """Parser: web search commands."""

    @pytest.mark.parametrize(
        "cmd,expected_query",
        [
            ("search for python tutorials", "python tutorials"),
            ("google machine learning", "machine learning"),
            ("search python documentation", "python documentation"),
            ("look up fastapi docs", "fastapi docs"),
            ("web search react hooks", "react hooks"),
        ],
    )
    def test_search_web(self, cmd: str, expected_query: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.SEARCH_WEB
        assert params["query"] == expected_query


class TestCloseApp:
    """Parser: close/kill app commands."""

    @pytest.mark.parametrize(
        "cmd,expected_app",
        [
            ("close chrome", "chrome"),
            ("kill notepad", "notepad"),
            ("quit firefox", "firefox"),
            ("exit vscode", "vscode"),
        ],
    )
    def test_close_known_app(self, cmd: str, expected_app: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.CLOSE_APP
        assert params["app_name"] == expected_app

    def test_close_unknown_app_returns_none(self) -> None:
        # "close the door" should NOT match as a desktop command
        result = parse_desktop_command("close the door")
        assert result is None


class TestScreenshot:
    """Parser: screenshot commands."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "take a screenshot",
            "screenshot",
            "take screenshot",
            "capture screen",
            "screen capture",
        ],
    )
    def test_screenshot(self, cmd: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, _params = result
        assert action == DesktopAction.SCREENSHOT


class TestSystemInfo:
    """Parser: system info commands."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "system info",
            "system information",
            "my computer specs",
            "pc info",
            "laptop specs",
            "show system info",
        ],
    )
    def test_system_info(self, cmd: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, _params = result
        assert action == DesktopAction.SYSTEM_INFO


class TestVolumeControl:
    """Parser: volume control commands."""

    @pytest.mark.parametrize(
        "cmd,expected_direction",
        [
            ("volume up", "up"),
            ("volume down", "down"),
            ("mute", "mute"),
            ("unmute", "unmute"),
            ("turn up the volume", "up"),
            ("increase volume", "up"),
            ("decrease volume", "down"),
        ],
    )
    def test_volume_control(self, cmd: str, expected_direction: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.VOLUME_CONTROL
        assert params["direction"] == expected_direction


class TestTypeText:
    """Parser: type text commands."""

    @pytest.mark.parametrize(
        "cmd,expected_text",
        [
            ("type hello world", "hello world"),
            ("type out this message", "out this message"),
        ],
    )
    def test_type_text(self, cmd: str, expected_text: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, params = result
        assert action == DesktopAction.TYPE_TEXT
        assert params["text"] == expected_text


class TestListRunning:
    """Parser: list running apps commands."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "list running apps",
            "show running applications",
            "what apps are running",
            "active applications",
            "running programs",
        ],
    )
    def test_list_running(self, cmd: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is not None
        action, _params = result
        assert action == DesktopAction.LIST_RUNNING


class TestNonDesktopCommands:
    """Ensure career/chat commands DO NOT match desktop patterns."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "find python jobs",
            "hello",
            "help",
            "tailor job 1",
            "status",
            "analyze my resume",
            "career advice",
            "what can you do",
            "prepare for interview",
            "",
        ],
    )
    def test_non_desktop_returns_none(self, cmd: str) -> None:
        result = parse_desktop_command(cmd)
        assert result is None
