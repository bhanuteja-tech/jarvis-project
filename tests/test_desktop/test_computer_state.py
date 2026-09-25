"""Tests for ComputerState tracking, conversational context, and search results caching."""

from app.desktop.state import ComputerState


def test_computer_state_initialization():
    state = ComputerState()
    assert state.active_application is None
    assert state.current_directory is not None
    assert state.last_search_results == []


def test_computer_state_context_updates():
    state = ComputerState()

    # Step 1: Open Chrome
    state.update(
        active_application="Google Chrome",
        browser={"name": "chrome", "current_url": "https://google.com"},
        last_action="open_application",
    )
    assert state.active_application == "Google Chrome"
    assert state.browser["name"] == "chrome"

    # Step 2: Open YouTube
    state.update(
        current_url="https://youtube.com",
        last_action="browser_navigate",
    )
    assert state.current_url == "https://youtube.com"

    # Step 3: Open Desktop
    state.update(
        active_application="File Explorer",
        current_directory="C:\\Users\\User\\Desktop",
        last_action="open_folder",
    )
    assert state.active_application == "File Explorer"
    assert "Desktop" in state.current_directory


def test_computer_state_caching_search_results():
    state = ComputerState()
    matches = [{"name": "resume.pdf", "path": "C:\\Desktop\\resume.pdf", "type": "file"}]
    state.last_search_results = matches
    assert len(state.last_search_results) == 1
    assert state.last_search_results[0]["name"] == "resume.pdf"
