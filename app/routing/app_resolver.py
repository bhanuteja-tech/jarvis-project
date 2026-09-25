"""Centralized Application Resolver for JARVIS.

Resolves user-uttered application names, aliases, and speech-recognition
corruptions into canonical applications and executable paths on the host system.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedApplication:
    """Authoritative result of resolving an application on the system."""

    canonical_name: str
    executable: str | None
    source: str
    display_name: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "executable": self.executable,
            "source": self.source,
            "display_name": self.display_name,
            "confidence": self.confidence,
        }


# Authoritative application registry with aliases, executables, and common paths
APPLICATION_CATALOG: dict[str, dict[str, Any]] = {
    "visual_studio_code": {
        "display_name": "Visual Studio Code",
        "aliases": [
            "vs code",
            "vscode",
            "visual studio code",
            "visual studio",
            "bs code",
            "code",
            "v s code",
            "v.s. code",
            "vs-code",
        ],
        "executables": ["code.cmd", "code.exe", "code"],
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
        ],
        "process_names": ["code.exe", "code"],
        "window_keywords": ["visual studio code", " - code"],
    },
    "google_chrome": {
        "display_name": "Google Chrome",
        "aliases": ["chrome", "google chrome", "google-chrome", "googlechrome"],
        "executables": ["chrome.exe", "chrome"],
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "process_names": ["chrome.exe"],
        "window_keywords": ["google chrome", "chrome"],
    },
    "microsoft_edge": {
        "display_name": "Microsoft Edge",
        "aliases": ["edge", "microsoft edge", "msedge", "ms edge"],
        "executables": ["msedge.exe", "msedge"],
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "process_names": ["msedge.exe"],
        "window_keywords": ["microsoft edge", "edge"],
    },
    "file_explorer": {
        "display_name": "File Explorer",
        "aliases": [
            "file explorer",
            "windows explorer",
            "explorer",
            "files",
            "my files",
            "explorer.exe",
        ],
        "executables": ["explorer.exe", "explorer"],
        "paths": [r"C:\Windows\explorer.exe"],
        "process_names": ["explorer.exe"],
        "window_keywords": ["file explorer", "explorer"],
    },
    "notepad": {
        "display_name": "Notepad",
        "aliases": ["notepad", "note pad"],
        "executables": ["notepad.exe", "notepad"],
        "paths": [r"C:\Windows\System32\notepad.exe", r"C:\Windows\notepad.exe"],
        "process_names": ["notepad.exe"],
        "window_keywords": ["notepad"],
    },
    "calculator": {
        "display_name": "Calculator",
        "aliases": ["calculator", "calc"],
        "executables": ["calc.exe", "calc"],
        "paths": [r"C:\Windows\System32\calc.exe"],
        "process_names": ["calculatorapp.exe", "calc.exe"],
        "window_keywords": ["calculator"],
    },
    "terminal": {
        "display_name": "Terminal",
        "aliases": [
            "terminal",
            "windows terminal",
            "command prompt",
            "cmd",
            "powershell",
            "pwsh",
        ],
        "executables": ["wt.exe", "powershell.exe", "cmd.exe"],
        "paths": [
            r"C:\Windows\System32\cmd.exe",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        ],
        "process_names": ["windowsterminal.exe", "cmd.exe", "powershell.exe"],
        "window_keywords": ["command prompt", "powershell", "terminal"],
    },
    "spotify": {
        "display_name": "Spotify",
        "aliases": ["spotify"],
        "executables": ["spotify.exe", "spotify"],
        "paths": [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")],
        "process_names": ["spotify.exe"],
        "window_keywords": ["spotify"],
    },
    "discord": {
        "display_name": "Discord",
        "aliases": ["discord"],
        "executables": ["discord.exe", "discord"],
        "paths": [os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")],
        "process_names": ["discord.exe"],
        "window_keywords": ["discord"],
    },
    "slack": {
        "display_name": "Slack",
        "aliases": ["slack"],
        "executables": ["slack.exe", "slack"],
        "paths": [os.path.expandvars(r"%LOCALAPPDATA%\slack\slack.exe")],
        "process_names": ["slack.exe"],
        "window_keywords": ["slack"],
    },
    "firefox": {
        "display_name": "Mozilla Firefox",
        "aliases": ["firefox", "mozilla firefox"],
        "executables": ["firefox.exe", "firefox"],
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "process_names": ["firefox.exe"],
        "window_keywords": ["firefox"],
    },
    "whatsapp": {
        "display_name": "WhatsApp",
        "aliases": ["whatsapp", "whats app", "whatsapp desktop", "whatsapp messenger"],
        "executables": ["WhatsApp.exe", "whatsapp.exe", "whatsapp"],
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\WhatsApp\WhatsApp.exe"),
        ],
        "process_names": ["whatsapp.exe", "whatsapp"],
        "window_keywords": ["whatsapp"],
        "uri_protocol": "whatsapp:",
    },
}


class ApplicationResolver:
    """Central resolver locating executables across OS sources without hardcoding."""

    def __init__(self, catalog: dict[str, dict[str, Any]] | None = None) -> None:
        self.catalog = catalog or APPLICATION_CATALOG
        self._alias_map: dict[str, str] = {}
        self._build_alias_map()

    def _build_alias_map(self) -> None:
        """Index all aliases down to their canonical name."""
        for canonical, spec in self.catalog.items():
            self._alias_map[canonical.lower()] = canonical
            display = spec.get("display_name", "")
            if display:
                self._alias_map[display.lower()] = canonical
            for alias in spec.get("aliases", []):
                self._alias_map[alias.lower().strip()] = canonical

    def canonicalize(self, name_or_alias: str) -> str | None:
        """Map raw user or STT string to canonical application name."""
        if not name_or_alias:
            return None
        clean = name_or_alias.lower().strip().strip(".'\"")
        # Direct lookup
        if clean in self._alias_map:
            return self._alias_map[clean]

        # Normalized lookup (strip 'the', 'app', 'application')
        for prefix in ("the ", "app ", "application "):
            if clean.startswith(prefix):
                sub = clean[len(prefix) :].strip()
                if sub in self._alias_map:
                    return self._alias_map[sub]

        for suffix in (" app", " application"):
            if clean.endswith(suffix):
                sub = clean[: -len(suffix)].strip()
                if sub in self._alias_map:
                    return self._alias_map[sub]

        return None

    def get_display_name(self, canonical_name: str) -> str:
        spec = self.catalog.get(canonical_name)
        if spec:
            return spec.get("display_name", canonical_name.replace("_", " ").title())
        return canonical_name.replace("_", " ").title()

    def resolve(self, name_or_alias: str) -> ResolvedApplication | None:
        """Locate executable and runtime metadata for the requested application."""
        canonical = self.canonicalize(name_or_alias)
        if not canonical:
            return None

        spec = self.catalog.get(canonical, {})
        display = spec.get("display_name", canonical.replace("_", " ").title())
        confidence = 0.98 if name_or_alias.lower().strip() == canonical else 0.95
        if "bs code" in name_or_alias.lower():
            confidence = 0.92

        # 1. Check known file paths
        for path_str in spec.get("paths", []):
            try:
                p = Path(path_str)
                if p.is_file():
                    return ResolvedApplication(
                        canonical_name=canonical,
                        executable=str(p.resolve()),
                        source="KNOWN_PATH",
                        display_name=display,
                        confidence=confidence,
                    )
            except (PermissionError, OSError):
                continue

        # 2. Check PATH via shutil.which
        for exe in spec.get("executables", []):
            found = shutil.which(exe)
            if found:
                return ResolvedApplication(
                    canonical_name=canonical,
                    executable=found,
                    source="PATH",
                    display_name=display,
                    confidence=confidence,
                )

        # 3. Check Start Menu shortcuts
        shortcut = self._find_start_menu_shortcut(canonical, spec)
        if shortcut:
            return ResolvedApplication(
                canonical_name=canonical,
                executable=str(shortcut),
                source="START_MENU",
                display_name=display,
                confidence=confidence,
            )

        # 4. Check Windows Registry App Paths
        reg_path = self._find_registry_app_path(spec.get("executables", []))
        if reg_path:
            return ResolvedApplication(
                canonical_name=canonical,
                executable=reg_path,
                source="REGISTRY",
                display_name=display,
                confidence=confidence,
            )

        # 5. Check URI protocol handler (e.g. "whatsapp:")
        uri_proto = spec.get("uri_protocol")
        if uri_proto:
            return ResolvedApplication(
                canonical_name=canonical,
                executable=uri_proto,
                source="URI_PROTOCOL",
                display_name=display,
                confidence=0.90,
            )

        # 6. Fallback: executable name for system launch if registered
        exes = spec.get("executables", [])
        primary_exe = exes[0] if exes else f"{canonical}.exe"
        return ResolvedApplication(
            canonical_name=canonical,
            executable=primary_exe,
            source="DEFAULT_FALLBACK",
            display_name=display,
            confidence=0.80,
        )

    def _find_start_menu_shortcut(self, canonical: str, spec: dict[str, Any]) -> Path | None:
        """Scan Windows Start Menu directories for matching .lnk shortcuts."""
        start_menu_dirs = [
            Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
            Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
        ]
        keywords = [canonical.replace("_", " "), spec.get("display_name", "").lower()]
        keywords.extend(spec.get("aliases", []))
        keywords = [k.lower() for k in keywords if k]

        for s_dir in start_menu_dirs:
            if not s_dir.is_dir():
                continue
            try:
                for lnk in s_dir.rglob("*.lnk"):
                    lnk_lower = lnk.stem.lower()
                    if any(kw in lnk_lower for kw in keywords):
                        return lnk.resolve()
            except (PermissionError, OSError):
                continue
        return None

    def _find_registry_app_path(self, executable_names: list[str]) -> str | None:
        """Look up executable registered in Windows App Paths registry."""
        try:
            import winreg

            subkeys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            ]
            for hkey, base_path in subkeys:
                for exe in executable_names:
                    try:
                        with winreg.OpenKey(hkey, f"{base_path}\\{exe}") as key:
                            val, _ = winreg.QueryValueEx(key, "")
                            if val and Path(val).exists():
                                return val
                    except OSError:
                        continue
        except ImportError:
            pass
        return None


# Global singleton application resolver
default_app_resolver = ApplicationResolver()
