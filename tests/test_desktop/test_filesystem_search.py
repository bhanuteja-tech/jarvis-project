"""Tests for filesystem search without hallucination."""

from app.desktop.filesystem_controller import FileSystemController
from app.desktop.state import ComputerState


def test_search_files_real_matches(tmp_path):
    # Create test files
    f1 = tmp_path / "resume_john_doe.pdf"
    f1.write_text("dummy resume content")
    f2 = tmp_path / "notes.txt"
    f2.write_text("some notes")
    f3 = tmp_path / "VS Code.lnk"
    f3.write_text("shortcut target")

    state = ComputerState()
    fs = FileSystemController(state=state)

    # Search for resume
    res = fs.search_files(directory=str(tmp_path), query="resume")
    assert res["success"]
    assert res["count"] == 1
    assert res["matches"][0]["name"] == "resume_john_doe.pdf"
    assert len(state.last_search_results) == 1

    # Search for VS Code
    res_code = fs.search_files(directory=str(tmp_path), query="vscode")
    assert res_code["success"]
    assert res_code["count"] == 0

    res_code2 = fs.search_files(directory=str(tmp_path), query="vs code")
    assert res_code2["success"]
    assert res_code2["count"] == 1
    assert res_code2["matches"][0]["name"] == "VS Code.lnk"


def test_search_files_zero_hallucination(tmp_path):
    state = ComputerState()
    fs = FileSystemController(state=state)

    res = fs.search_files(directory=str(tmp_path), query="non_existent_file_xyz_123")
    assert res["success"]
    assert res["count"] == 0
    assert len(res["matches"]) == 0
    assert "couldn't find" in res["message"].lower()
