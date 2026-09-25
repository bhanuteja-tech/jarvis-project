"""Safety guardrails for desktop control.

All validations are allow-list based: only curated app names, safe URL
schemes, and non-system file paths are permitted. Nothing here is
configurable from user input.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Allowed applications registry: friendly name -> list of possible executable
# names / commands. The executor tries each in order via shutil.which().
# ---------------------------------------------------------------------------

ALLOWED_APPS: dict[str, list[str]] = {
    # Browsers
    "chrome": ["chrome", "google-chrome", "google-chrome-stable"],
    "google chrome": ["chrome", "google-chrome", "google-chrome-stable"],
    "firefox": ["firefox"],
    "edge": ["msedge", "microsoft-edge"],
    "microsoft edge": ["msedge", "microsoft-edge"],
    "brave": ["brave", "brave-browser"],
    # Editors / IDEs
    "notepad": ["notepad"],
    "notepad++": ["notepad++"],
    "vscode": ["code"],
    "visual studio code": ["code"],
    "vs code": ["code"],
    "sublime": ["subl", "sublime_text"],
    # System utilities
    "calculator": ["calc"],
    "calc": ["calc"],
    "task manager": ["taskmgr"],
    "file explorer": ["explorer"],
    "explorer": ["explorer"],
    "cmd": ["cmd"],
    "command prompt": ["cmd"],
    "powershell": ["powershell"],
    "terminal": ["wt", "cmd"],
    "windows terminal": ["wt"],
    "paint": ["mspaint"],
    "snipping tool": ["snippingtool", "SnippingTool"],
    "settings": ["ms-settings:"],
    "control panel": ["control"],
    # Media
    "spotify": ["spotify"],
    "vlc": ["vlc"],
    # Communication
    "discord": ["discord"],
    "slack": ["slack"],
    "teams": ["teams"],
    "microsoft teams": ["teams"],
    "zoom": ["zoom"],
    # Development
    "git bash": ["git-bash"],
    "postman": ["postman"],
    "docker": ["docker"],
    # Office
    "word": ["winword"],
    "microsoft word": ["winword"],
    "excel": ["excel"],
    "microsoft excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "microsoft powerpoint": ["powerpnt"],
    "outlook": ["outlook"],
}

# Applications that can be closed via taskkill. Subset of ALLOWED_APPS —
# system-critical processes are never killable.
CLOSEABLE_APPS: dict[str, list[str]] = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "firefox": ["firefox.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "brave": ["brave.exe"],
    "browser": ["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"],
    "notepad": ["notepad.exe"],
    "notepad++": ["notepad++.exe"],
    "vscode": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "vs code": ["Code.exe"],
    "calculator": ["Calculator.exe", "calc.exe"],
    "calc": ["Calculator.exe", "calc.exe"],
    "paint": ["mspaint.exe"],
    "spotify": ["Spotify.exe"],
    "vlc": ["vlc.exe"],
    "discord": ["Discord.exe"],
    "slack": ["slack.exe"],
    "teams": ["Teams.exe", "ms-teams.exe"],
    "zoom": ["Zoom.exe"],
    "word": ["WINWORD.EXE"],
    "excel": ["EXCEL.EXE"],
    "powerpoint": ["POWERPNT.EXE"],
    "outlook": ["OUTLOOK.EXE"],
    "postman": ["Postman.exe"],
}

# ---------------------------------------------------------------------------
# Blocked file paths — system directories that must never be opened/modified.
# ---------------------------------------------------------------------------

_SYSTEM_ROOTS_WIN = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information",
]

BLOCKED_PATH_PREFIXES: list[str] = [p.lower().replace("\\", "/") for p in _SYSTEM_ROOTS_WIN]

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}
_DANGEROUS_URL_RE = re.compile(r"javascript:|data:|vbscript:|file://", re.IGNORECASE)


def sanitize_url(url: str) -> str | None:
    """Validate and return a safe URL, or None if unsafe.

    Only http:// and https:// schemes are permitted. No javascript:,
    data:, vbscript:, or file:// URLs are allowed.
    """
    url = url.strip()
    if not url:
        return None

    # Auto-prefix scheme for bare domains
    if not url.startswith(("http://", "https://")):
        # Reject URLs with other schemes (ftp://, etc.)
        if "://" in url:
            return None
        if "." in url and not url.startswith(("javascript:", "data:", "file:")):
            url = "https://" + url
        else:
            return None

    if _DANGEROUS_URL_RE.search(url):
        return None

    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return None

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return None
    if not parsed.netloc:
        return None

    return url


# ---------------------------------------------------------------------------
# App name validation
# ---------------------------------------------------------------------------


def validate_app_name(name: str) -> str | None:
    """Return the normalized app name if it is in the allow-list, else None."""
    normalized = name.strip().lower()
    if normalized in ALLOWED_APPS:
        return normalized
    return None


# ---------------------------------------------------------------------------
# File path validation
# ---------------------------------------------------------------------------


def is_safe_file_path(path_str: str) -> bool:
    """Check if a file path is safe to open (exists and not in system dirs)."""
    try:
        path = Path(path_str).resolve()
    except (OSError, ValueError):
        return False

    normalized = str(path).lower().replace("\\", "/")
    for prefix in BLOCKED_PATH_PREFIXES:
        if normalized.startswith(prefix):
            return False

    return path.exists()


__all__ = [
    "ALLOWED_APPS",
    "BLOCKED_PATH_PREFIXES",
    "CLOSEABLE_APPS",
    "is_safe_file_path",
    "sanitize_url",
    "validate_app_name",
]
