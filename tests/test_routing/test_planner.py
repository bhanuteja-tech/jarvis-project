"""Tests for multi-action execution planner."""

from app.routing.planner import default_planner


def test_single_command_planning():
    steps = default_planner.plan("Open Chrome")
    assert len(steps) == 1
    assert steps[0] == "Open Chrome"


def test_compound_and_then_planning():
    steps = default_planner.plan("Open VS Code and then open my project")
    assert len(steps) == 2
    assert "open vs code" in steps[0].lower()
    assert "open my project" in steps[1].lower()


def test_compound_comma_sequence():
    steps = default_planner.plan("Open Chrome, go to YouTube, and search Campus X")
    assert len(steps) == 3
    assert "open chrome" in steps[0].lower()
    assert "go to youtube" in steps[1].lower()
    assert "search campus x" in steps[2].lower()


def test_compound_navigate_and_search():
    steps = default_planner.plan("Navigate to my Desktop and search for vscode")
    assert len(steps) == 2
    assert "desktop" in steps[0].lower()
    assert "search" in steps[1].lower()
