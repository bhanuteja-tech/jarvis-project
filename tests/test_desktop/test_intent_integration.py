"""Tests for intent.py desktop_control integration."""

from __future__ import annotations

import pytest

from app.jarvis.intent import parse_intent


class TestDesktopIntentRouting:
    """Verify desktop commands route to desktop_control action."""

    @pytest.mark.parametrize(
        "text,expected_desktop_action",
        [
            ("open chrome", "open_app"),
            ("launch notepad", "open_app"),
            ("go to github.com", "open_url"),
            ("search for python tutorials", "search_web"),
            ("close chrome", "close_app"),
            ("take a screenshot", "screenshot"),
            ("system info", "system_info"),
            ("volume up", "volume_control"),
            ("mute", "volume_control"),
            ("list running apps", "list_running"),
        ],
    )
    def test_desktop_commands_route_correctly(
        self, text: str, expected_desktop_action: str
    ) -> None:
        plan = parse_intent(text)
        assert plan.action == "desktop_control"
        assert plan.intent == "desktop_control"
        assert plan.params["desktop_action"] == expected_desktop_action
        assert plan.from_free_text is False

    @pytest.mark.parametrize(
        "text,expected_action",
        [
            ("find python jobs in bangalore", "run_discovery"),
            ("tailor job 1", "select_target"),
            ("hello", "casual_chat"),
            ("help", "help"),
            ("status", "get_results"),
            ("analyze my resume", "resume_analysis"),
            ("career advice", "career_advice"),
        ],
    )
    def test_non_desktop_commands_unaffected(self, text: str, expected_action: str) -> None:
        plan = parse_intent(text)
        assert plan.action == expected_action
