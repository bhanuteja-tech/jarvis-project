"""Board registry behavior: file-backed loading, tolerance, replaceability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.sources.errors import SourceConfigurationError
from app.sources.greenhouse.registry import (
    FileBoardRegistry,
    NullBoardRegistry,
    load_board_registry,
)


class TestNullRegistry:
    def test_load_board_registry_without_path_returns_null_registry(self) -> None:
        registry = load_board_registry(None)

        assert isinstance(registry, NullBoardRegistry)
        assert registry.company_for("anything") is None


class TestFileBoardRegistry:
    def test_resolves_configured_tokens(self, tmp_path: Path) -> None:
        path = tmp_path / "boards.json"
        path.write_text(json.dumps({"examplecorp": "Example Corp"}), encoding="utf-8")

        registry = FileBoardRegistry(path)

        assert registry.company_for("examplecorp") == "Example Corp"
        assert registry.company_for("unknown") is None

    def test_missing_file_behaves_like_empty_registry(self, tmp_path: Path) -> None:
        registry = FileBoardRegistry(tmp_path / "does_not_exist.json")

        assert registry.company_for("examplecorp") is None

    def test_non_string_values_are_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "boards.json"
        path.write_text(
            json.dumps({"good": "Good Co", "bad": 42, "blank": "   "}),
            encoding="utf-8",
        )

        registry = FileBoardRegistry(path)

        assert registry.company_for("good") == "Good Co"
        assert registry.company_for("bad") is None
        assert registry.company_for("blank") is None

    def test_invalid_json_is_a_configuration_error(self, tmp_path: Path) -> None:
        path = tmp_path / "boards.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(SourceConfigurationError):
            FileBoardRegistry(path).company_for("examplecorp")

    def test_non_object_json_is_a_configuration_error(self, tmp_path: Path) -> None:
        path = tmp_path / "boards.json"
        path.write_text(json.dumps(["a", "b"]), encoding="utf-8")

        with pytest.raises(SourceConfigurationError):
            FileBoardRegistry(path).company_for("examplecorp")
