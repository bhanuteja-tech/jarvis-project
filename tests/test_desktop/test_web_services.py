"""Tests for web services catalog and URL resolvers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.desktop.vault import CredentialVault
from app.desktop.web_services import (
    find_service,
    resolve_service_request,
)


@pytest.fixture
def temp_vault(tmp_path: Path) -> CredentialVault:
    vault_file = tmp_path / "credentials.json"
    return CredentialVault(vault_file)


class TestWebServicesCatalog:
    def test_find_service_by_name(self) -> None:
        spec = find_service("github")
        assert spec is not None
        assert spec.name == "github"
        assert spec.display_name == "GitHub"

    def test_find_service_by_alias(self) -> None:
        assert find_service("gh") is not None
        assert find_service("gh").name == "github"
        assert find_service("yt") is not None
        assert find_service("yt").name == "youtube"
        assert find_service("hn") is not None
        assert find_service("hn").name == "hackernews"
        assert find_service("hacker news") is not None
        assert find_service("hacker news").name == "hackernews"

    def test_find_unknown_service_returns_none(self) -> None:
        assert find_service("nonexistentservicexyz") is None
        assert find_service("") is None


class TestResolveServiceRequest:
    def test_resolve_base_url(self, temp_vault: CredentialVault) -> None:
        res = resolve_service_request("youtube", vault=temp_vault)
        assert res.success is True
        assert res.url == "https://youtube.com"
        assert res.needs_credential is False

    def test_resolve_search_query(self, temp_vault: CredentialVault) -> None:
        res = resolve_service_request("youtube", query="lofi hip hop", vault=temp_vault)
        assert res.success is True
        assert "lofi+hip+hop" in res.url or "lofi" in res.url
        assert "youtube.com/results?search_query=" in res.url

    def test_resolve_github_account_without_credential(self, temp_vault: CredentialVault) -> None:
        res = resolve_service_request("github", account=True, vault=temp_vault)
        assert res.success is False
        assert res.needs_credential is True
        assert res.service == "github"
        assert res.field == "username"
        assert "GitHub" in res.message

    def test_resolve_github_account_with_credential(self, temp_vault: CredentialVault) -> None:
        temp_vault.set_field("github", "username", "bhanuteja-tech")
        res = resolve_service_request("github", account=True, vault=temp_vault)
        assert res.success is True
        assert res.needs_credential is False
        assert res.url == "https://github.com/bhanuteja-tech"
        assert "bhanuteja-tech" in res.message

    def test_resolve_hackernews(self, temp_vault: CredentialVault) -> None:
        res = resolve_service_request("hackernews", vault=temp_vault)
        assert res.success is True
        assert res.url == "https://news.ycombinator.com"
