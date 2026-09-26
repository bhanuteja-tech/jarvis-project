"""End-to-End Regression Test: Multi-turn Music Context Flow

Verifies the 4-turn sequence from Section 35 of the specification:
Turn 1: "open Music"
Turn 2: "how many files are present"
Turn 3: "what are those files"
Turn 4: "open the third one"

Assertions:
- filesystem context remains authoritative
- directory entities are persisted
- "those files" resolves to filesystem_results
- "third one" resolves to filesystem_results
- no Google search
- no YouTube entity resolution
- active browser state cannot override the filesystem context
"""

from __future__ import annotations

from typing import Any

import pytest

from app.computer.agent import LLMComputerAgent
from app.computer.context import YouTubeVideoEntity
from app.desktop.observer import ComputerObserver
from app.desktop.state import ComputerState
from app.desktop.verifier import VerificationService


class MockMusicHarness:
    """Mock execution harness providing realistic filesystem responses."""

    def __init__(self, state: ComputerState) -> None:
        self.state = state
        self.executed_tools: list[tuple[str, dict[str, Any]]] = []
        self.verified_files = [
            "fileA.mp3",
            "fileB.mp3",
            "fileC.wav",
            "fileD.mp3",
            "notes.txt",
            "song.flac",
        ]

    def open_folder(self, path: str) -> dict[str, Any]:
        self.executed_tools.append(("open_folder", {"path": path}))
        self.state.current_directory = path
        self.state.active_application = "File Explorer"
        self.state.active_window_title = f"{path} - File Explorer"
        return {"success": True, "action": "open_folder", "path": path}

    def count_directory_items(
        self, directory: str | None = None, item_type: str = "file"
    ) -> dict[str, Any]:
        target = directory or self.state.current_directory or "Music"
        self.executed_tools.append(
            ("count_directory_items", {"directory": target, "item_type": item_type})
        )
        count = len(self.verified_files)
        msg = f"There are {count} {item_type}s present in the {target} folder."
        return {
            "success": True,
            "action": "count_directory_items",
            "directory": target,
            "dir_name": target,
            "item_type": item_type,
            "count": count,
            "file_count": count,
            "folder_count": 0,
            "files": self.verified_files,
            "folders": [],
            "message": msg,
        }

    def list_directory(self, directory: str | None = None) -> dict[str, Any]:
        target = directory or self.state.current_directory or "Music"
        self.executed_tools.append(("list_directory", {"directory": target}))
        return {
            "success": True,
            "action": "list_directory",
            "directory": target,
            "dir_name": target,
            "files": self.verified_files,
            "folders": [],
        }

    def open_file(self, path: str) -> dict[str, Any]:
        self.executed_tools.append(("open_file", {"path": path}))
        self.state.selected_file = path
        return {"success": True, "action": "open_file", "path": path}

    def browser_search(
        self, query: str, site: str = "google", browser: str | None = None
    ) -> dict[str, Any]:
        self.executed_tools.append(
            ("browser_search", {"query": query, "site": site, "browser": browser})
        )
        return {"success": True, "action": "browser_search", "query": query}

    def browser_click(self, target: str, ordinal: int | None = None) -> dict[str, Any]:
        self.executed_tools.append(("browser_click", {"target": target, "ordinal": ordinal}))
        return {"success": True, "action": "browser_click", "target": target}


@pytest.mark.asyncio
async def test_music_context_four_turn_flow() -> None:
    """Verify the 4-turn Music context sequence from problem statement."""
    state = ComputerState()
    state.reset()
    harness = MockMusicHarness(state)

    agent = LLMComputerAgent(
        state=state,
        harness=harness,
        observer=ComputerObserver(state=state),
        verifier=VerificationService(),
    )

    # Pre-seed stale browser state & YouTube entities to strictly verify that
    # active browser state CANNOT override the filesystem context!
    agent.typed_context.youtube_video_results = [
        YouTubeVideoEntity(
            ordinal=1,
            title="Video 1",
            url="https://youtube.com/v1",
            source="browser_dom_cdp",
        ),
        YouTubeVideoEntity(
            ordinal=2,
            title="Video 2",
            url="https://youtube.com/v2",
            source="browser_dom_cdp",
        ),
        YouTubeVideoEntity(
            ordinal=3,
            title="Video 3",
            url="https://youtube.com/v3",
            source="browser_dom_cdp",
        ),
    ]
    state.active_application = "Google Chrome"
    state.current_url = "https://www.youtube.com"

    # =========================================================================
    # TURN 1: "open Music"
    # =========================================================================
    ev1 = [ev async for ev in agent.run("open Music")]
    assert any(ev.get("tool") == "open_folder" for ev in ev1)
    assert agent.typed_context.last_active_domain == "filesystem"
    assert agent.typed_context.last_opened_folder == "Music"
    # YouTube entities MUST be purged when filesystem opens
    assert len(agent.typed_context.youtube_video_results) == 0

    # =========================================================================
    # TURN 2: "how many files are present"
    # =========================================================================
    ev2 = [ev async for ev in agent.run("how many files are present")]
    assert any(ev.get("tool") == "count_directory_items" for ev in ev2)
    resp2 = next(ev.get("text") for ev in ev2 if ev.get("agent_event_type") == "response")
    assert "6" in resp2 or "files" in resp2.lower()
    # Directory entities are persisted in typed_context
    assert len(agent.typed_context.filesystem_results) == 6
    assert agent.typed_context.filesystem_results[0].name == "fileA.mp3"
    assert agent.typed_context.filesystem_results[2].name == "fileC.wav"

    # =========================================================================
    # TURN 3: "what are those files"
    # =========================================================================
    ev3 = [ev async for ev in agent.run("what are those files")]
    # Must NOT execute any browser search or Google search
    assert not any(call[0] == "browser_search" for call in harness.executed_tools)
    assert not any(call[0] == "browser_navigate" for call in harness.executed_tools)
    # Response resolves against current verified filesystem context
    resp3 = next(ev.get("text") for ev in ev3 if ev.get("agent_event_type") == "response")
    assert "fileA.mp3" in resp3
    assert "fileB.mp3" in resp3
    assert "fileC.wav" in resp3

    # =========================================================================
    # TURN 4: "open the third one"
    # =========================================================================
    ev4 = [ev async for ev in agent.run("open the third one")]
    # MUST resolve to 3rd filesystem item ("fileC.wav"), NOT a YouTube video!
    assert any(ev.get("tool") == "open_file" for ev in ev4)
    open_file_calls = [c for c in harness.executed_tools if c[0] == "open_file"]
    assert len(open_file_calls) >= 1
    assert "fileC.wav" in open_file_calls[-1][1].get("path", "")

    # STRICT ASSERTIONS ACROSS ALL TURNS:
    # 1. No Google search ever occurred
    for call in harness.executed_tools:
        assert call[0] != "browser_search", f"Forbidden browser_search found: {call}"
    # 2. No YouTube click occurred
    for call in harness.executed_tools:
        assert call[0] != "browser_click", f"Forbidden browser_click found: {call}"
    # 3. Active domain remained filesystem
    assert agent.typed_context.last_active_domain == "filesystem"
