"""Desktop control module for local laptop automation.

Provides safe, allow-listed desktop operations: open apps, URLs,
search the web, take screenshots, close apps, volume control, etc.
All operations are deterministic, stdlib-only (no external API keys),
and execute on the same machine as the FastAPI server.
"""

from app.desktop.actions import ActionResult, DesktopAction
from app.desktop.executor import DesktopExecutor
from app.desktop.parser import parse_desktop_command
from app.desktop.safety import ALLOWED_APPS, is_safe_file_path, sanitize_url, validate_app_name

__all__ = [
    "ActionResult",
    "ALLOWED_APPS",
    "DesktopAction",
    "DesktopExecutor",
    "is_safe_file_path",
    "parse_desktop_command",
    "sanitize_url",
    "validate_app_name",
]
