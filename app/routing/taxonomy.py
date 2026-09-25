"""First-class intent taxonomy for the JARVIS agent architecture.

Defines strongly-typed Intent enums, categories, and risk classifications.
Prevents generic "search" catch-alls by distinguishing computer, browser,
filesystem, and career search operations.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class Intent(StrEnum):
    """Authoritative intent enum for all JARVIS capabilities."""

    # ---- Computer & Application Control ----------------------------------
    OPEN_APPLICATION = "open_application"
    CLOSE_APPLICATION = "close_application"
    FOCUS_APPLICATION = "focus_application"

    # ---- Filesystem & Folders --------------------------------------------
    OPEN_FOLDER = "open_folder"
    NAVIGATE_FOLDER = "navigate_folder"
    LIST_FILES = "list_files"
    SEARCH_FILES = "search_files"
    OPEN_FILE = "open_file"

    # ---- Browser Control -------------------------------------------------
    OPEN_WEBSITE = "open_website"
    NAVIGATE_WEBSITE = "navigate_website"
    BROWSER_OPEN = "browser_open"
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_SEARCH = "browser_search"
    BROWSER_BACK = "browser_back"
    BROWSER_FORWARD = "browser_forward"
    OPEN_TAB = "open_tab"
    CLOSE_TAB = "close_tab"
    SWITCH_TAB = "switch_tab"
    BROWSER_NEW_TAB = "browser_new_tab"
    BROWSER_CLOSE_TAB = "browser_close_tab"

    # ---- Web Entity Hierarchy -------------------------------------------
    OPEN_CHANNEL = "open_channel"
    OPEN_PLAYLIST = "open_playlist"
    OPEN_COURSE = "open_course"
    OPEN_VIDEO = "open_video"
    OPEN_RESULT = "open_result"
    SELECT_RESULT = "select_result"
    SCROLL_TO_RESULT = "scroll_to_result"
    OPEN_REFERENCE = "open_reference"

    # ---- Screen & UI Interaction -----------------------------------------
    SCREEN_READ = "screen_read"
    SCREEN_ANALYZE = "screen_analyze"
    READ_SCREEN = "read_screen"
    UI_CLICK = "ui_click"
    UI_TYPE = "ui_type"
    UI_SELECT = "ui_select"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"

    # ---- External Actions & Messaging ------------------------------------
    OPEN_CONTACT = "open_contact"
    COMPOSE_MESSAGE = "compose_message"
    SEND_MESSAGE = "send_message"
    MESSAGING_SEND = "messaging_send"
    CONFIRM_ACTION = "confirm_action"
    REJECT_ACTION = "reject_action"

    # ---- Career Intelligence Workflows -----------------------------------
    CAREER_JOB_SEARCH = "career_job_search"
    CAREER_JOB_ANALYSIS = "career_job_analysis"
    CAREER_RESUME_TAILOR = "career_resume_tailor"
    CAREER_MATCHING = "career_matching"

    # ---- Conversational & Session Control --------------------------------
    GENERAL_CONVERSATION = "general_conversation"
    VOICE_SESSION_START = "voice_session_start"
    VOICE_SESSION_STOP = "voice_session_stop"
    INTERRUPT = "interrupt"


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

# Action Risk Classification
RISK_LEVELS: dict[Intent, RiskLevel] = {
    # Low risk (read-only or safe navigation/focus)
    Intent.OPEN_APPLICATION: "LOW",
    Intent.FOCUS_APPLICATION: "LOW",
    Intent.OPEN_FOLDER: "LOW",
    Intent.NAVIGATE_FOLDER: "LOW",
    Intent.LIST_FILES: "LOW",
    Intent.SEARCH_FILES: "LOW",
    Intent.OPEN_FILE: "LOW",
    Intent.OPEN_WEBSITE: "LOW",
    Intent.NAVIGATE_WEBSITE: "LOW",
    Intent.BROWSER_OPEN: "LOW",
    Intent.BROWSER_NAVIGATE: "LOW",
    Intent.BROWSER_SEARCH: "LOW",
    Intent.BROWSER_BACK: "LOW",
    Intent.BROWSER_FORWARD: "LOW",
    Intent.OPEN_TAB: "LOW",
    Intent.CLOSE_TAB: "LOW",
    Intent.SWITCH_TAB: "LOW",
    Intent.BROWSER_NEW_TAB: "LOW",
    Intent.BROWSER_CLOSE_TAB: "LOW",
    Intent.OPEN_CHANNEL: "LOW",
    Intent.OPEN_PLAYLIST: "LOW",
    Intent.OPEN_COURSE: "LOW",
    Intent.OPEN_VIDEO: "LOW",
    Intent.OPEN_RESULT: "LOW",
    Intent.SELECT_RESULT: "LOW",
    Intent.SCROLL_TO_RESULT: "LOW",
    Intent.OPEN_REFERENCE: "LOW",
    Intent.SCREEN_READ: "LOW",
    Intent.SCREEN_ANALYZE: "LOW",
    Intent.READ_SCREEN: "LOW",
    Intent.SCROLL: "LOW",
    Intent.GENERAL_CONVERSATION: "LOW",
    Intent.VOICE_SESSION_START: "LOW",
    Intent.VOICE_SESSION_STOP: "LOW",
    Intent.INTERRUPT: "LOW",
    Intent.CAREER_JOB_SEARCH: "LOW",
    Intent.CAREER_JOB_ANALYSIS: "LOW",
    Intent.CAREER_RESUME_TAILOR: "LOW",
    Intent.CAREER_MATCHING: "LOW",
    Intent.CONFIRM_ACTION: "LOW",
    Intent.REJECT_ACTION: "LOW",
    # Medium risk
    Intent.CLOSE_APPLICATION: "MEDIUM",
    Intent.UI_CLICK: "MEDIUM",
    Intent.UI_TYPE: "MEDIUM",
    Intent.UI_SELECT: "MEDIUM",
    Intent.CLICK: "MEDIUM",
    Intent.TYPE: "MEDIUM",
    Intent.SELECT: "MEDIUM",
    Intent.COMPOSE_MESSAGE: "MEDIUM",
    Intent.OPEN_CONTACT: "LOW",
    # High risk (requires explicit confirmation)
    Intent.MESSAGING_SEND: "HIGH",
    Intent.SEND_MESSAGE: "HIGH",
}


def is_computer_control(intent: Intent) -> bool:
    """Return True if intent controls local OS, apps, windows, messaging, or filesystem."""
    return intent in {
        Intent.OPEN_APPLICATION,
        Intent.CLOSE_APPLICATION,
        Intent.FOCUS_APPLICATION,
        Intent.OPEN_FOLDER,
        Intent.NAVIGATE_FOLDER,
        Intent.LIST_FILES,
        Intent.SEARCH_FILES,
        Intent.OPEN_FILE,
        Intent.SCREEN_READ,
        Intent.SCREEN_ANALYZE,
        Intent.READ_SCREEN,
        Intent.UI_CLICK,
        Intent.UI_TYPE,
        Intent.UI_SELECT,
        Intent.CLICK,
        Intent.TYPE,
        Intent.SELECT,
        Intent.SCROLL,
        Intent.OPEN_CONTACT,
        Intent.COMPOSE_MESSAGE,
        Intent.SEND_MESSAGE,
        Intent.MESSAGING_SEND,
        Intent.CONFIRM_ACTION,
        Intent.REJECT_ACTION,
    }


def is_browser_control(intent: Intent) -> bool:
    """Return True if intent controls web browser operations."""
    return intent in {
        Intent.OPEN_WEBSITE,
        Intent.NAVIGATE_WEBSITE,
        Intent.BROWSER_OPEN,
        Intent.BROWSER_NAVIGATE,
        Intent.BROWSER_SEARCH,
        Intent.BROWSER_BACK,
        Intent.BROWSER_FORWARD,
        Intent.OPEN_TAB,
        Intent.CLOSE_TAB,
        Intent.SWITCH_TAB,
        Intent.BROWSER_NEW_TAB,
        Intent.BROWSER_CLOSE_TAB,
        Intent.OPEN_CHANNEL,
        Intent.OPEN_PLAYLIST,
        Intent.OPEN_COURSE,
        Intent.OPEN_VIDEO,
        Intent.OPEN_RESULT,
        Intent.SELECT_RESULT,
        Intent.SCROLL_TO_RESULT,
        Intent.OPEN_REFERENCE,
    }


def is_career_intent(intent: Intent) -> bool:
    """Return True if intent specifically targets the career intelligence graph."""
    return intent in {
        Intent.CAREER_JOB_SEARCH,
        Intent.CAREER_JOB_ANALYSIS,
        Intent.CAREER_RESUME_TAILOR,
        Intent.CAREER_MATCHING,
    }


def is_session_control(intent: Intent) -> bool:
    """Return True if intent alters voice session lifecycle."""
    return intent in {
        Intent.VOICE_SESSION_START,
        Intent.VOICE_SESSION_STOP,
        Intent.INTERRUPT,
    }


def get_action_risk(intent: Intent) -> RiskLevel:
    """Return the RiskLevel for the specified Intent, defaulting to LOW."""
    return RISK_LEVELS.get(intent, "LOW")


__all__ = [
    "Intent",
    "RiskLevel",
    "RISK_LEVELS",
    "get_action_risk",
    "is_computer_control",
    "is_browser_control",
    "is_career_intent",
    "is_session_control",
]
