"""Event envelope contract."""

from __future__ import annotations

from app.jarvis.events import EventType, make_event


def test_envelope_shape() -> None:
    event = make_event(EventType.WORKFLOW_NODE_COMPLETED, seq=3,
                       run_id="r1", node="rank_jobs")

    assert event["type"] == "workflow_node_completed"
    assert event["seq"] == 3
    assert event["run_id"] == "r1"
    assert event["data"] == {"node": "rank_jobs"}
    assert "ts" in event


def test_all_documented_types_exist() -> None:
    expected = {
        "agent_started", "agent_thinking", "tool_started", "tool_progress",
        "tool_completed", "workflow_node_started", "workflow_node_completed",
        "token", "assistant_message", "listening_started",
        "completed", "error",
    }
    actual = {member.value for member in EventType}
    assert expected <= actual
