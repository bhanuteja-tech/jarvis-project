"""In-memory session store behavior."""

from __future__ import annotations

from app.jarvis.sessions import InMemorySessionStore


def test_get_or_create_is_stable_per_id() -> None:
    store = InMemorySessionStore()
    session = store.get_or_create("s1")

    assert store.get_or_create("s1") is session
    assert store.get_or_create(None).session_id != "s1"


def test_message_history_append() -> None:
    store = InMemorySessionStore()
    session = store.get_or_create("s1")

    session.append_message("user", "find python jobs")
    session.append_message("assistant", "Working on it.")

    assert [m["role"] for m in session.messages] == ["user", "assistant"]


def test_candidate_input_persists_across_turns() -> None:
    store = InMemorySessionStore()
    session = store.get_or_create("s1")
    session.candidate_input = {"text": "my resume"}

    assert store.get("s1").candidate_input == {"text": "my resume"}
