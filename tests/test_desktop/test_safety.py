"""Tests for the desktop safety module (allow-lists and validators)."""

from __future__ import annotations

import pytest

from app.desktop.safety import (
    is_safe_file_path,
    sanitize_url,
    validate_app_name,
)


class TestSanitizeUrl:
    """URL validation and sanitization."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://google.com", "https://google.com"),
            ("http://example.com", "http://example.com"),
            ("google.com", "https://google.com"),
            ("www.github.com", "https://www.github.com"),
            ("https://example.com/path?q=1", "https://example.com/path?q=1"),
        ],
    )
    def test_valid_urls(self, url: str, expected: str) -> None:
        assert sanitize_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,hello",
            "file:///etc/passwd",
            "vbscript:msgbox",
            "",
            "   ",
            "ftp://example.com",
            "not-a-url",
        ],
    )
    def test_invalid_urls(self, url: str) -> None:
        assert sanitize_url(url) is None


class TestValidateAppName:
    """App name allow-list validation."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("chrome", "chrome"),
            ("Chrome", "chrome"),
            ("  notepad  ", "notepad"),
            ("VSCODE", "vscode"),
            ("visual studio code", "visual studio code"),
            ("file explorer", "file explorer"),
        ],
    )
    def test_valid_apps(self, name: str, expected: str) -> None:
        assert validate_app_name(name) == expected

    @pytest.mark.parametrize(
        "name",
        [
            "nonexistent_app",
            "virus.exe",
            "",
            "rm -rf /",
            "cmd && del *",
        ],
    )
    def test_invalid_apps(self, name: str) -> None:
        assert validate_app_name(name) is None


class TestIsSafeFilePath:
    """File path safety validation."""

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Windows\System32\cmd.exe",
            r"C:\Program Files\something",
            r"C:\ProgramData\secret",
        ],
    )
    def test_blocked_paths(self, path: str) -> None:
        assert is_safe_file_path(path) is False

    def test_nonexistent_path(self) -> None:
        assert is_safe_file_path(r"C:\this\path\does\not\exist\file.txt") is False
