"""Tests for strongly-typed Intent taxonomy, risk levels, and predicates."""

from app.routing.taxonomy import (
    Intent,
    get_action_risk,
    is_browser_control,
    is_career_intent,
    is_computer_control,
    is_session_control,
)


def test_intent_taxonomy_completeness():
    assert Intent.OPEN_APPLICATION.value == "open_application"
    assert Intent.CLOSE_APPLICATION.value == "close_application"
    assert Intent.FOCUS_APPLICATION.value == "focus_application"
    assert Intent.OPEN_FOLDER.value == "open_folder"
    assert Intent.NAVIGATE_FOLDER.value == "navigate_folder"
    assert Intent.LIST_FILES.value == "list_files"
    assert Intent.SEARCH_FILES.value == "search_files"
    assert Intent.OPEN_FILE.value == "open_file"

    assert Intent.BROWSER_OPEN.value == "browser_open"
    assert Intent.BROWSER_NAVIGATE.value == "browser_navigate"
    assert Intent.BROWSER_SEARCH.value == "browser_search"
    assert Intent.BROWSER_BACK.value == "browser_back"
    assert Intent.BROWSER_FORWARD.value == "browser_forward"

    assert Intent.CAREER_JOB_SEARCH.value == "career_job_search"
    assert Intent.GENERAL_CONVERSATION.value == "general_conversation"


def test_risk_levels():
    assert get_action_risk(Intent.OPEN_APPLICATION) == "LOW"
    assert get_action_risk(Intent.OPEN_FOLDER) == "LOW"
    assert get_action_risk(Intent.SEARCH_FILES) == "LOW"
    assert get_action_risk(Intent.BROWSER_NAVIGATE) == "LOW"
    assert get_action_risk(Intent.CLOSE_APPLICATION) == "MEDIUM"


def test_intent_predicates():
    assert is_computer_control(Intent.OPEN_APPLICATION)
    assert is_computer_control(Intent.SEARCH_FILES)
    assert not is_computer_control(Intent.CAREER_JOB_SEARCH)

    assert is_browser_control(Intent.BROWSER_NAVIGATE)
    assert is_browser_control(Intent.BROWSER_SEARCH)
    assert not is_browser_control(Intent.OPEN_FOLDER)

    assert is_career_intent(Intent.CAREER_JOB_SEARCH)
    assert is_career_intent(Intent.CAREER_RESUME_TAILOR)
    assert not is_career_intent(Intent.SEARCH_FILES)

    assert is_session_control(Intent.VOICE_SESSION_START)
    assert is_session_control(Intent.VOICE_SESSION_STOP)
    assert is_session_control(Intent.INTERRUPT)
    assert not is_session_control(Intent.OPEN_APPLICATION)
