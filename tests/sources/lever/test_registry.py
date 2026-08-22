"""Site registry behavior: file-backed loading, tolerance, replaceability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.sources.errors import SourceConfigurationError
from app.sources.lever.registry import (
    FileSiteRegistry,
    NullSiteRegistry,
    load_site_registry,
)


class TestNullRegistry:
    def test_load_site_registry_without_path_returns_null_registry(self) -> None:
        registry = load_site_registry(None)

        assert isinstance(registry, NullSiteRegistry)
        assert registry.company_for("anything") is None


class TestFileSiteRegistry:
    def test_resolves_configured_sites(self, tmp_path: Path) -> None:
        path = tmp_path / "sites.json"
        path.write_text(json.dumps({"leverdemo": "Lever Demo Co"}), encoding="utf-8")

        registry = FileSiteRegistry(path)

        assert registry.company_for("leverdemo") == "Lever Demo Co"
        assert registry.company_for("unknown") is None

    def test_missing_file_behaves_like_empty_registry(self, tmp_path: Path) -> None:
        registry = FileSiteRegistry(tmp_path / "does_not_exist.json")

        assert registry.company_for("leverdemo") is None

    def test_non_string_values_are_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "sites.json"
        path.write_text(
            json.dumps({"good": "Good Co", "bad": 42, "blank": "   "}),
            encoding="utf-8",
        )

        registry = FileSiteRegistry(path)

        assert registry.company_for("good") == "Good Co"
        assert registry.company_for("bad") is None
        assert registry.company_for("blank") is None

    def test_invalid_json_is_a_configuration_error(self, tmp_path: Path) -> None:
        path = tmp_path / "sites.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(SourceConfigurationError):
            FileSiteRegistry(path).company_for("leverdemo")

    def test_non_object_json_is_a_configuration_error(self, tmp_path: Path) -> None:
        path = tmp_path / "sites.json"
        path.write_text(json.dumps(["a", "b"]), encoding="utf-8")

        with pytest.raises(SourceConfigurationError):
            FileSiteRegistry(path).company_for("leverdemo")
