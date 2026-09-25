"""Tests for CredentialVault."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.desktop.vault import CredentialVault


@pytest.fixture
def temp_vault(tmp_path: Path) -> CredentialVault:
    vault_file = tmp_path / "credentials.json"
    return CredentialVault(vault_file)


class TestCredentialVault:
    def test_empty_vault_get_returns_none(self, temp_vault: CredentialVault) -> None:
        assert temp_vault.get("github") is None
        assert temp_vault.get_field("github", "username") is None
        assert temp_vault.has("github") is False
        assert temp_vault.list_services() == []

    def test_set_and_get_service(self, temp_vault: CredentialVault) -> None:
        ok = temp_vault.set("github", {"username": "bhanuteja-tech"})
        assert ok is True
        assert temp_vault.has("github") is True
        assert temp_vault.has("github", required_field="username") is True
        assert temp_vault.has("github", required_field="token") is False
        assert temp_vault.get("github") == {"username": "bhanuteja-tech"}
        assert temp_vault.get_field("github", "username") == "bhanuteja-tech"
        assert "github" in temp_vault.list_services()

    def test_set_field_updates_existing(self, temp_vault: CredentialVault) -> None:
        temp_vault.set("github", {"username": "bhanuteja-tech"})
        temp_vault.set_field("github", "token", "ghp_secret")
        creds = temp_vault.get("github")
        assert creds is not None
        assert creds["username"] == "bhanuteja-tech"
        assert creds["token"] == "ghp_secret"

    def test_case_insensitivity(self, temp_vault: CredentialVault) -> None:
        temp_vault.set("GitHub", {"username": "bhanuteja-tech"})
        assert temp_vault.get("github") == {"username": "bhanuteja-tech"}
        assert temp_vault.get_field("GITHUB", "username") == "bhanuteja-tech"
        assert temp_vault.has("github") is True

    def test_delete_service(self, temp_vault: CredentialVault) -> None:
        temp_vault.set("github", {"username": "bhanuteja-tech"})
        assert temp_vault.delete("github") is True
        assert temp_vault.has("github") is False
        assert temp_vault.delete("github") is False

    def test_corrupted_json_recovery(self, tmp_path: Path) -> None:
        vault_file = tmp_path / "credentials.json"
        vault_file.write_text("invalid json content", encoding="utf-8")
        vault = CredentialVault(vault_file)
        assert vault.get("github") is None
        assert vault.list_services() == []
        # Should be able to overwrite cleanly
        assert vault.set("github", {"username": "test"}) is True
        assert vault.get_field("github", "username") == "test"
