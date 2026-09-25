"""Deterministic regex-based parser for desktop control commands.

Maps natural-language voice/text input to a (DesktopAction, params) tuple.
Returns None when the input is not a desktop command, allowing the existing
intent system to handle it (career workflows, casual chat, etc.).
"""

from __future__ import annotations

import re
from typing import Any

from app.desktop.actions import DesktopAction
from app.desktop.web_services import find_service

# ---------------------------------------------------------------------------
# Regex patterns for desktop command detection
# ---------------------------------------------------------------------------

# "open chrome", "launch notepad", "start calculator", "run vscode", "go to github"
_OPEN_APP_RE = re.compile(
    r"^(?:open|launch|start|run|go\s+to|visit|navigate\s+to|browse\s+to)\s+(?:the\s+)?(?:app(?:lication)?\s+)?(.+?)(?:\s+app(?:lication)?)?$",
    re.IGNORECASE,
)

# "go to github.com", "open youtube.com", "visit google.com",
# "navigate to example.com", "open https://..."
_OPEN_URL_RE = re.compile(
    r"^(?:open|go\s+to|visit|navigate\s+to|browse\s+to)\s+"
    r"((?:https?://)?[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+(?:/\S*)?)$",
    re.IGNORECASE,
)

# "search for python tutorials", "google machine learning", "look up fastapi docs"
_SEARCH_WEB_RE = re.compile(
    r"^(?:search(?:\s+(?:for|the\s+web\s+for))?\s+|google\s+|look\s+up\s+|web\s+search\s+)(.+)$",
    re.IGNORECASE,
)

# Career keywords that indicate job discovery rather than a desktop web search
_CAREER_KEYWORD_RE = re.compile(
    r"\b(?:jobs?|internships?|roles?|positions?|openings?|vacanc(?:y|ies))\b",
    re.IGNORECASE,
)

# "play lofi on youtube", "watch trailers on youtube"
_PLAY_YOUTUBE_RE = re.compile(
    r"^(?:play|watch)\s+(.+?)(?:\s+(?:on|in)\s+(?:youtube|yt))$",
    re.IGNORECASE,
)

# "search youtube for lofi", "search on youtube for lofi"
_SERVICE_SEARCH_RE = re.compile(
    r"^search\s+(?:on\s+|in\s+)?(youtube|yt|github|gh|google|reddit|amazon|spotify|hackernews|hn|wikipedia|wiki|stackoverflow)\s+for\s+(.+)$",
    re.IGNORECASE,
)

# "close chrome", "kill notepad", "quit firefox", "exit vscode"
_CLOSE_APP_RE = re.compile(
    r"^(?:close|kill|quit|exit|stop|end)\s+(?:the\s+)?(.+?)(?:\s+app(?:lication)?)?$",
    re.IGNORECASE,
)

# "take a screenshot", "screenshot", "capture screen", "screen capture"
_SCREENSHOT_RE = re.compile(
    r"^(?:take\s+a?\s*)?(?:screen\s*shot|screen\s*capture|capture\s+(?:the\s+)?screen|snap\s+screen)"
    r"|^screenshot$",
    re.IGNORECASE,
)

# "what apps are running", "list running apps", "show running processes",
# "running programs", "active apps"
_LIST_RUNNING_RE = re.compile(
    r"^(?:(?:list|show|what(?:'s|\s+are)?)\s+)?(?:running|active|open)\s+"
    r"(?:apps?|applications?|programs?|processes?|windows?)"
    r"|^(?:list|show)\s+(?:apps?|applications?|programs?|processes?|windows?)$"
    r"|^what\s+(?:apps?|applications?|programs?)\s+are\s+(?:running|active|open)$",
    re.IGNORECASE,
)

# "system info", "my computer specs", "system specs", "pc info",
# "computer info", "show system information"
_SYSTEM_INFO_RE = re.compile(
    r"^(?:(?:show|get|what(?:'s|\s+is)?)\s+)?(?:(?:my\s+)?(?:system|computer|pc|laptop|machine)"
    r"\s+(?:info(?:rmation)?|specs?|details?|status))"
    r"|^system\s+info(?:rmation)?$"
    r"|^(?:pc|computer|laptop)\s+(?:info|specs?)$",
    re.IGNORECASE,
)

# "volume up", "volume down", "mute", "unmute", "turn up the volume"
_VOLUME_RE = re.compile(
    r"^(?:(?:turn|set)\s+)?(?:the\s+)?volume\s+(up|down|mute|unmute|max|min)"
    r"|^(mute|unmute)(?:\s+(?:the\s+)?(?:volume|sound|audio))?$"
    r"|^(?:increase|raise)\s+(?:the\s+)?volume$"
    r"|^(?:decrease|lower|reduce)\s+(?:the\s+)?volume$"
    r"|^turn\s+(up|down)\s+(?:the\s+)?volume$",
    re.IGNORECASE,
)

# "type hello world", "type out this text", "write hello"
_TYPE_TEXT_RE = re.compile(
    r"^(?:type|type\s+out|write|enter\s+text)\s+(.+)$",
    re.IGNORECASE,
)

# "open file C:\Users\...\report.pdf", "open document report.txt"
_OPEN_FILE_RE = re.compile(
    r"^(?:open|show|view)\s+(?:the\s+)?(?:file|document)\s+(.+[/\\].+|.+\..+)$",
    re.IGNORECASE,
)

_URL_LIKE_RE = re.compile(
    r"^(?:https?://|www\.)|"
    r"(?:\.com|\.org|\.net|\.io|\.dev|\.co|\.me|\.app|\.ai|\.edu|\.gov)(?:/|$)",
    re.IGNORECASE,
)


def parse_desktop_command(text: str) -> tuple[DesktopAction, dict[str, Any]] | None:
    """Parse a user command into a desktop action + params.

    Returns None when the text does not match any desktop command pattern,
    signalling the caller to fall through to the existing intent system.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    cleaned_norm = cleaned.rstrip(".?!").strip()

    # ---- Screenshot (check early, no target extraction) -------------------
    if _SCREENSHOT_RE.search(cleaned):
        return DesktopAction.SCREENSHOT, {}

    # ---- List running apps -----------------------------------------------
    if _LIST_RUNNING_RE.search(cleaned):
        return DesktopAction.LIST_RUNNING, {}

    # ---- System info -----------------------------------------------------
    if _SYSTEM_INFO_RE.search(cleaned):
        return DesktopAction.SYSTEM_INFO, {}

    # ---- Navigate back ---------------------------------------------------
    if re.match(r"^(?:go\s+back|navigate\s+back|back)$", cleaned_norm, re.IGNORECASE):
        return DesktopAction.NAVIGATE_BACK, {}

    # ---- Open Desktop ---------------------------------------------------
    if re.match(r"^(?:open|show|go\s+to|view)\s+(?:the\s+)?desktop$", cleaned_norm, re.IGNORECASE):
        return DesktopAction.OPEN_DESKTOP, {}

    # ---- List Files in current directory --------------------------------
    if re.match(
        r"^(?:what\s+files\s+(?:are\s+)?(?:available|there|here)|list\s+(?:the\s+)?files|show\s+(?:the\s+)?files|what's\s+in\s+this\s+folder|what's\s+on\s+my\s+desktop|show\s+files|dir)$",
        cleaned_norm,
        re.IGNORECASE,
    ):
        return DesktopAction.LIST_FILES, {}

    # ---- Open Resume ----------------------------------------------------
    if re.match(
        r"^(?:open|show|view|find)\s+(?:my\s+)?(?:resume|cv)$", cleaned_norm, re.IGNORECASE
    ):
        return DesktopAction.OPEN_RESUME, {}

    # ---- Volume control --------------------------------------------------
    vol_match = _VOLUME_RE.search(cleaned)
    if vol_match:
        direction = _extract_volume_direction(cleaned, vol_match)
        return DesktopAction.VOLUME_CONTROL, {"direction": direction}

    # ---- Specific Service Searches (e.g. YouTube play / search) ---------
    yt_play_match = _PLAY_YOUTUBE_RE.match(cleaned)
    if yt_play_match:
        q = yt_play_match.group(1).strip()
        return DesktopAction.SEARCH_WEB, {"query": q, "service": "youtube"}

    svc_search_match = _SERVICE_SEARCH_RE.match(cleaned)
    if svc_search_match:
        svc_name = svc_search_match.group(1).strip().lower()
        q = svc_search_match.group(2).strip()
        return DesktopAction.SEARCH_WEB, {"query": q, "service": svc_name}

    # ---- URL opening (before app open to catch "open youtube.com") -------
    url_match = _OPEN_URL_RE.match(cleaned)
    if url_match:
        return DesktopAction.OPEN_URL, {"url": url_match.group(1).strip()}

    # ---- Web search (before app open to catch "search for ...") ----------
    search_match = _SEARCH_WEB_RE.match(cleaned)
    if search_match:
        query = search_match.group(1).strip()
        # Do not hijack career job queries (e.g. "search data science jobs")
        if query and not _CAREER_KEYWORD_RE.search(query):
            return DesktopAction.SEARCH_WEB, {"query": query}

    # ---- Close app -------------------------------------------------------
    close_match = _CLOSE_APP_RE.match(cleaned)
    if close_match:
        target = close_match.group(1).strip().lower()
        from app.desktop.safety import CLOSEABLE_APPS

        if target in CLOSEABLE_APPS:
            return DesktopAction.CLOSE_APP, {"app_name": target}

    # ---- Type text -------------------------------------------------------
    type_match = _TYPE_TEXT_RE.match(cleaned)
    if type_match:
        text_to_type = type_match.group(1).strip()
        if text_to_type:
            return DesktopAction.TYPE_TEXT, {"text": text_to_type}

    # ---- Open file -------------------------------------------------------
    file_match = _OPEN_FILE_RE.match(cleaned)
    if file_match:
        file_path = file_match.group(1).strip()
        if file_path:
            return DesktopAction.OPEN_FILE, {"path": file_path}

    # ---- Open app / Browser / Web Service --------------------------------
    app_match = _OPEN_APP_RE.match(cleaned)
    if app_match:
        target = app_match.group(1).strip()
        target_lower = target.lower()

        # 1. Check if user wants to open the browser itself
        browser_synonyms = {
            "browser",
            "a browser",
            "the browser",
            "web browser",
            "internet browser",
        }
        if target_lower in browser_synonyms:
            return DesktopAction.OPEN_BROWSER, {}

        # 3. Check for "my <service>" (e.g. "open my github")
        m_my = re.match(r"^my\s+([a-zA-Z0-9_\-\.\s]+?)(?:\s+(?:account|profile))?$", target_lower)
        if m_my:
            cand = m_my.group(1).strip()
            spec = find_service(cand)
            if spec:
                return DesktopAction.OPEN_SERVICE, {"service": spec.name, "account": True}

        m_acc = re.match(r"^([a-zA-Z0-9_\-\.\s]+?)\s+(?:account|profile)$", target_lower)
        if m_acc:
            cand = m_acc.group(1).strip()
            spec = find_service(cand)
            if spec:
                return DesktopAction.OPEN_SERVICE, {"service": spec.name, "account": True}

        # 4. If target is a known native desktop app (e.g. spotify, chrome, notepad, discord)
        from app.desktop.safety import validate_app_name

        if validate_app_name(target) is not None:
            return DesktopAction.OPEN_APP, {"app_name": target_lower}

        # 5. Check for direct web service (e.g. "open youtube", "open github", "open linkedin")
        spec = find_service(target_lower)
        if spec:
            is_personal = spec.name == "github"
            return DesktopAction.OPEN_SERVICE, {"service": spec.name, "account": is_personal}

        # 6. If target looks like a URL, route to OPEN_URL instead
        if _URL_LIKE_RE.search(target):
            return DesktopAction.OPEN_URL, {"url": target}

    return None


def _extract_volume_direction(text: str, match: re.Match) -> str:
    """Normalize the volume direction from various phrasings."""
    lowered = text.lower()
    if "mute" in lowered and "unmute" not in lowered:
        return "mute"
    if "unmute" in lowered:
        return "unmute"
    if any(w in lowered for w in ("increase", "raise", "up", "max")):
        return "up"
    if any(w in lowered for w in ("decrease", "lower", "reduce", "down", "min")):
        return "down"
    # Fallback: use group captures
    g1 = match.group(1)
    g2 = match.group(2) if match.lastindex and match.lastindex >= 2 else None
    direction = (g1 or g2 or "").strip().lower()
    return direction if direction in {"up", "down", "mute", "unmute", "max", "min"} else "up"


__all__ = ["parse_desktop_command"]
