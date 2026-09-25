"""Desktop action executor — the core engine for local laptop control.

Every public method returns an ``ActionResult``. No method raises; all
failures are reported through the result's ``success=False`` path.
Only allow-listed operations are supported; there is no arbitrary
command execution.

Platform: Windows (PowerShell fallbacks). Runs server-side on the same
machine the user wants to control.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import webbrowser
from typing import Any
from urllib.parse import quote_plus

from app.desktop.actions import ActionResult, DesktopAction
from app.desktop.safety import (
    ALLOWED_APPS,
    CLOSEABLE_APPS,
    is_safe_file_path,
    sanitize_url,
    validate_app_name,
)

logger = logging.getLogger(__name__)


class DesktopExecutor:
    """Stateless executor for curated desktop operations.

    Cheap to create — no state, no connections. Safe for one-shot use
    per incoming command.
    """

    def execute(self, action: DesktopAction, params: dict[str, Any]) -> ActionResult:
        """Dispatch to the appropriate handler. Never raises."""
        handlers = {
            DesktopAction.OPEN_APP: self._open_application,
            DesktopAction.OPEN_URL: self._open_url,
            DesktopAction.SEARCH_WEB: self._search_web,
            DesktopAction.OPEN_FILE: self._open_file,
            DesktopAction.SYSTEM_INFO: self._get_system_info,
            DesktopAction.SCREENSHOT: self._take_screenshot,
            DesktopAction.TYPE_TEXT: self._type_text,
            DesktopAction.VOLUME_CONTROL: self._control_volume,
            DesktopAction.CLOSE_APP: self._close_application,
            DesktopAction.LIST_RUNNING: self._list_running_apps,
        }
        handler = handlers.get(action)
        if handler is None:
            return ActionResult(
                success=False,
                message=f"Unknown action: {action}",
                action=str(action),
            )
        try:
            return handler(params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("desktop action %s failed: %s", action, exc, exc_info=True)
            return ActionResult(
                success=False,
                message=f"Failed to execute {action}: {exc}",
                action=str(action),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _open_application(self, params: dict[str, Any]) -> ActionResult:
        """Open an allow-listed application."""
        raw_name = str(params.get("app_name", "")).strip()
        app_name = validate_app_name(raw_name)
        if app_name is None:
            return ActionResult(
                success=False,
                message=f"'{raw_name}' is not in the allowed applications list.",
                action=DesktopAction.OPEN_APP,
                details={"requested": raw_name},
            )

        candidates = ALLOWED_APPS[app_name]

        # Special handling for Windows Settings URI
        for candidate in candidates:
            if candidate.startswith("ms-"):
                try:
                    os.startfile(candidate)
                    return ActionResult(
                        success=True,
                        message=f"Opened {app_name}.",
                        action=DesktopAction.OPEN_APP,
                        details={"app": app_name, "method": "startfile"},
                    )
                except OSError:
                    continue

        # Try shutil.which for each candidate
        for candidate in candidates:
            exe_path = shutil.which(candidate)
            if exe_path:
                subprocess.Popen(  # noqa: S603
                    [exe_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_detached_flags(),
                )
                logger.info("opened app=%s via path=%s", app_name, exe_path)
                return ActionResult(
                    success=True,
                    message=f"✅ Opened {app_name}.",
                    action=DesktopAction.OPEN_APP,
                    details={"app": app_name, "exe": exe_path},
                )

        # Fallback: try os.startfile on Windows (works for "calc", etc.)
        if os.name == "nt":
            for candidate in candidates:
                try:
                    os.startfile(candidate)
                    logger.info("opened app=%s via startfile=%s", app_name, candidate)
                    return ActionResult(
                        success=True,
                        message=f"✅ Opened {app_name}.",
                        action=DesktopAction.OPEN_APP,
                        details={"app": app_name, "method": "startfile"},
                    )
                except OSError:
                    continue

        return ActionResult(
            success=False,
            message=f"Could not find '{app_name}' on this system. "
            "Make sure it is installed and in your PATH.",
            action=DesktopAction.OPEN_APP,
            details={"app": app_name, "tried": candidates},
        )

    def _open_url(self, params: dict[str, Any]) -> ActionResult:
        """Open a validated URL in the default browser."""
        raw_url = str(params.get("url", "")).strip()
        safe_url = sanitize_url(raw_url)
        if safe_url is None:
            return ActionResult(
                success=False,
                message=f"'{raw_url}' is not a safe URL. Only http/https URLs are allowed.",
                action=DesktopAction.OPEN_URL,
                details={"requested": raw_url},
            )

        webbrowser.open(safe_url)
        logger.info("opened url=%s", safe_url)
        return ActionResult(
            success=True,
            message=f"🌐 Opened {safe_url} in your default browser.",
            action=DesktopAction.OPEN_URL,
            details={"url": safe_url},
        )

    def _search_web(self, params: dict[str, Any]) -> ActionResult:
        """Open a Google search for the given query."""
        query = str(params.get("query", "")).strip()
        if not query:
            return ActionResult(
                success=False,
                message="No search query provided.",
                action=DesktopAction.SEARCH_WEB,
            )

        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        webbrowser.open(search_url)
        logger.info("web search query=%s", query)
        return ActionResult(
            success=True,
            message=f"🔍 Searching the web for '{query}'.",
            action=DesktopAction.SEARCH_WEB,
            details={"query": query, "url": search_url},
        )

    def _open_file(self, params: dict[str, Any]) -> ActionResult:
        """Open a file with the system default handler."""
        path_str = str(params.get("path", "")).strip()
        if not path_str:
            return ActionResult(
                success=False,
                message="No file path provided.",
                action=DesktopAction.OPEN_FILE,
            )

        if not is_safe_file_path(path_str):
            return ActionResult(
                success=False,
                message=f"Cannot open '{path_str}': file not found or path is restricted.",
                action=DesktopAction.OPEN_FILE,
                details={"path": path_str},
            )

        os.startfile(path_str)
        logger.info("opened file=%s", path_str)
        return ActionResult(
            success=True,
            message=f"📂 Opened {os.path.basename(path_str)}.",
            action=DesktopAction.OPEN_FILE,
            details={"path": path_str},
        )

    def _get_system_info(self, _params: dict[str, Any]) -> ActionResult:
        """Return basic system information."""
        info = {
            "os": f"{platform.system()} {platform.release()}",
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "cpu_count": os.cpu_count() or 0,
            "hostname": platform.node(),
            "python": platform.python_version(),
        }

        # Try to get memory info on Windows
        if os.name == "nt":
            try:
                result = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=_detached_flags(),
                )
                if result.returncode == 0 and result.stdout.strip():
                    total_bytes = int(result.stdout.strip())
                    info["total_memory_gb"] = round(total_bytes / (1024**3), 1)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass

        lines = [
            "💻 **System Information**",
            f"• OS: {info['os']} ({info['os_version']})",
            f"• Machine: {info['machine']}",
            f"• Processor: {info['processor']}",
            f"• CPU Cores: {info['cpu_count']}",
            f"• Hostname: {info['hostname']}",
        ]
        if "total_memory_gb" in info:
            lines.append(f"• Total RAM: {info['total_memory_gb']} GB")

        return ActionResult(
            success=True,
            message="\n".join(lines),
            action=DesktopAction.SYSTEM_INFO,
            details=info,
        )

    def _take_screenshot(self, _params: dict[str, Any]) -> ActionResult:
        """Take a screenshot using PowerShell on Windows."""
        if os.name != "nt":
            return ActionResult(
                success=False,
                message="Screenshots are only supported on Windows.",
                action=DesktopAction.SCREENSHOT,
            )

        # Use PowerShell to capture screen via .NET
        save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Jarvis_Screenshots")
        os.makedirs(save_dir, exist_ok=True)

        import time

        filename = f"jarvis_screenshot_{int(time.time())}.png"
        filepath = os.path.join(save_dir, filename)

        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bitmap.Save('{filepath.replace(chr(92), chr(92) + chr(92))}')
$graphics.Dispose()
$bitmap.Dispose()
"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_detached_flags(),
            )
            if result.returncode == 0 and os.path.exists(filepath):
                logger.info("screenshot saved to %s", filepath)
                return ActionResult(
                    success=True,
                    message=f"📸 Screenshot saved to {filepath}",
                    action=DesktopAction.SCREENSHOT,
                    details={"path": filepath},
                )
            return ActionResult(
                success=False,
                message=f"Screenshot capture failed: {result.stderr.strip()[:200]}",
                action=DesktopAction.SCREENSHOT,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message="Screenshot timed out.",
                action=DesktopAction.SCREENSHOT,
            )

    def _type_text(self, params: dict[str, Any]) -> ActionResult:
        """Type text using PowerShell SendKeys (Windows only)."""
        text = str(params.get("text", "")).strip()
        if not text:
            return ActionResult(
                success=False,
                message="No text provided to type.",
                action=DesktopAction.TYPE_TEXT,
            )

        if os.name != "nt":
            return ActionResult(
                success=False,
                message="Type text is only supported on Windows.",
                action=DesktopAction.TYPE_TEXT,
            )

        # Sanitize for SendKeys: escape special characters
        sanitized = (
            text.replace("{", "{{")
            .replace("}", "}}")
            .replace("+", "{+}")
            .replace("^", "{^}")
            .replace("%", "{%}")
            .replace("~", "{~}")
            .replace("(", "{(}")
            .replace(")", "{)}")
        )

        # Cap length to prevent abuse
        if len(sanitized) > 500:
            return ActionResult(
                success=False,
                message="Text too long (max 500 characters).",
                action=DesktopAction.TYPE_TEXT,
            )

        escaped = sanitized.replace(chr(39), chr(39) + chr(39))
        ps_command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"
        )

        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_detached_flags(),
            )
            if result.returncode == 0:
                return ActionResult(
                    success=True,
                    message=f'⌨️ Typed: "{text[:50]}{"..." if len(text) > 50 else ""}"',
                    action=DesktopAction.TYPE_TEXT,
                    details={"text": text[:100]},
                )
            return ActionResult(
                success=False,
                message=f"Failed to type text: {result.stderr.strip()[:200]}",
                action=DesktopAction.TYPE_TEXT,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message="Type text timed out.",
                action=DesktopAction.TYPE_TEXT,
            )

    def _control_volume(self, params: dict[str, Any]) -> ActionResult:
        """Control system volume via PowerShell/nircmd (Windows only)."""
        direction = str(params.get("direction", "")).strip().lower()
        if direction not in {"up", "down", "mute", "unmute", "max", "min"}:
            return ActionResult(
                success=False,
                message=f"Unknown volume direction: '{direction}'.",
                action=DesktopAction.VOLUME_CONTROL,
            )

        if os.name != "nt":
            return ActionResult(
                success=False,
                message="Volume control is only supported on Windows.",
                action=DesktopAction.VOLUME_CONTROL,
            )

        # Use PowerShell to send media key presses
        key_map = {
            "up": ("Volume Up", "0xAF"),  # VK_VOLUME_UP
            "max": ("Volume Max", "0xAF"),
            "down": ("Volume Down", "0xAE"),  # VK_VOLUME_DOWN
            "min": ("Volume Min", "0xAE"),
            "mute": ("Volume Mute", "0xAD"),  # VK_VOLUME_MUTE
            "unmute": ("Volume Unmute", "0xAD"),
        }

        label, vk_code = key_map[direction]
        # Send multiple key presses for up/down to make a noticeable change
        repeat = 5 if direction in {"up", "down"} else (20 if direction in {"max", "min"} else 1)

        ps_script = f"""
$code = @'
[DllImport("user32.dll")]
public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
'@
$k = Add-Type -MemberDefinition $code -Name 'VolumeKey' -Namespace 'Win32' -PassThru
for ($i = 0; $i -lt {repeat}; $i++) {{
    $k::keybd_event({vk_code}, 0, 0, [UIntPtr]::Zero)
    $k::keybd_event({vk_code}, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 50
}}
"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_detached_flags(),
            )
            emoji_map = {
                "up": "🔊",
                "max": "🔊",
                "down": "🔉",
                "min": "🔈",
                "mute": "🔇",
                "unmute": "🔊",
            }
            if result.returncode == 0:
                return ActionResult(
                    success=True,
                    message=f"{emoji_map.get(direction, '🔊')} {label}.",
                    action=DesktopAction.VOLUME_CONTROL,
                    details={"direction": direction},
                )
            return ActionResult(
                success=False,
                message=f"Volume control failed: {result.stderr.strip()[:200]}",
                action=DesktopAction.VOLUME_CONTROL,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message="Volume control timed out.",
                action=DesktopAction.VOLUME_CONTROL,
            )

    def _close_application(self, params: dict[str, Any]) -> ActionResult:
        """Close an allow-listed application via taskkill."""
        raw_name = str(params.get("app_name", "")).strip().lower()
        if raw_name not in CLOSEABLE_APPS:
            return ActionResult(
                success=False,
                message=f"Cannot close '{raw_name}': not in the allowed list.",
                action=DesktopAction.CLOSE_APP,
                details={"requested": raw_name},
            )

        process_names = CLOSEABLE_APPS[raw_name]
        closed = False

        for proc in process_names:
            try:
                result = subprocess.run(
                    ["taskkill", "/IM", proc, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=_detached_flags(),
                )
                if result.returncode == 0:
                    closed = True
                    logger.info("closed app=%s process=%s", raw_name, proc)
                    break
            except (subprocess.TimeoutExpired, OSError):
                continue

        if closed:
            return ActionResult(
                success=True,
                message=f"❌ Closed {raw_name}.",
                action=DesktopAction.CLOSE_APP,
                details={"app": raw_name},
            )
        return ActionResult(
            success=False,
            message=f"'{raw_name}' is not currently running or could not be closed.",
            action=DesktopAction.CLOSE_APP,
            details={"app": raw_name},
        )

    def _list_running_apps(self, _params: dict[str, Any]) -> ActionResult:
        """List user-facing running applications."""
        if os.name != "nt":
            return ActionResult(
                success=False,
                message="Listing running apps is only supported on Windows.",
                action=DesktopAction.LIST_RUNNING,
            )

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} "
                    "| Select-Object -Property Name, MainWindowTitle "
                    "| Sort-Object Name -Unique | Format-Table -AutoSize -Wrap",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_detached_flags(),
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                # Parse into a clean list
                lines = [ln.strip() for ln in output.split("\n") if ln.strip()]
                # Skip header lines (Name, ----)
                apps = []
                for line in lines:
                    if line.startswith("---") or line.lower().startswith("name"):
                        continue
                    parts = line.split(None, 1)
                    if parts:
                        name = parts[0]
                        title = parts[1] if len(parts) > 1 else ""
                        apps.append({"name": name, "title": title})

                if apps:
                    app_lines = [f"📋 **Running Applications** ({len(apps)} apps):"]
                    for app in apps[:30]:  # Cap display
                        title_part = f" — {app['title']}" if app["title"] else ""
                        app_lines.append(f"  • {app['name']}{title_part}")
                    if len(apps) > 30:
                        app_lines.append(f"  ... and {len(apps) - 30} more")
                    return ActionResult(
                        success=True,
                        message="\n".join(app_lines),
                        action=DesktopAction.LIST_RUNNING,
                        details={"apps": apps, "count": len(apps)},
                    )

            return ActionResult(
                success=True,
                message="No user-facing applications found running.",
                action=DesktopAction.LIST_RUNNING,
                details={"apps": [], "count": 0},
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message="Listing running apps timed out.",
                action=DesktopAction.LIST_RUNNING,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detached_flags() -> int:
    """Return process creation flags for detached (no console window) procs."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


__all__ = ["DesktopExecutor"]
