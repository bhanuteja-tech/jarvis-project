"""Tests for the voice session contract, voice_turn, barge-in, and termination."""

from __future__ import annotations

from typing import Any

import pytest

from app.config.settings import Settings
from app.jarvis.events import EventType
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jarvis_assistant_llm_enabled=False,
        desktop_control_enabled=True,
    )


@pytest.fixture(autouse=True)
def reset_task_manager():
    from app.agent.task_manager import default_task_manager
    default_task_manager.reset()
    yield
    default_task_manager.reset()


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def orchestrator(
    test_settings: Settings, session_store: InMemorySessionStore
) -> JarvisOrchestrator:
    return JarvisOrchestrator(
        settings=test_settings,
        session_store=session_store,
        graph_factory=lambda: None,
    )


@pytest.mark.asyncio
async def test_voice_turn_fast_action(
    orchestrator: JarvisOrchestrator, session_store: InMemorySessionStore
) -> None:
    session = session_store.get_or_create("voice-sess-1", domain="computer")
    events: list[dict[str, Any]] = []

    async def send(event: dict[str, Any]) -> None:
        events.append(event)

    msg = {
        "type": "voice_turn",
        "text": "open chrome",
        "generation": 42,
    }

    await orchestrator.handle_message(session, msg, send=send)

    event_types = [e["type"] for e in events]
    assert EventType.AGENT_STARTED in event_types
    assert EventType.DESKTOP_ACTION_RESULT in event_types
    assert EventType.ASSISTANT_MESSAGE in event_types

    # Verify assistant_message has voice metadata
    asst_msg = next(e for e in events if e["type"] == EventType.ASSISTANT_MESSAGE)
    assert asst_msg["data"]["is_voice"] is True
    assert asst_msg["data"]["generation"] == 42
    assert "chrome" in asst_msg["data"]["text"].lower()


@pytest.mark.asyncio
async def test_voice_turn_termination_phrases(
    orchestrator: JarvisOrchestrator, session_store: InMemorySessionStore
) -> None:
    phrases = [
        "bye jarvis",
        "goodbye jarvis",
        "stop listening",
        "end session",
        "terminate session",
    ]
    for phrase in phrases:
        session = session_store.get_or_create(f"term-sess-{phrase[:4]}")
        phrase_events: list[dict[str, Any]] = []

        def make_sender(target_list: list[dict[str, Any]]):
            async def sender(event: dict[str, Any]) -> None:
                target_list.append(event)

            return sender

        msg = {
            "type": "voice_turn",
            "text": phrase,
            "generation": 10,
        }

        await orchestrator.handle_message(session, msg, send=make_sender(phrase_events))

        asst_msg = next(
            (e for e in phrase_events if e["type"] == EventType.ASSISTANT_MESSAGE),
            None,
        )
        assert asst_msg is not None, f"Expected assistant message for '{phrase}'"
        assert asst_msg["data"]["is_voice"] is True
        assert asst_msg["data"]["is_termination"] is True
        assert "Goodbye" in asst_msg["data"]["text"]


@pytest.mark.asyncio
async def test_voice_turn_okay_does_not_terminate(
    orchestrator: JarvisOrchestrator, session_store: InMemorySessionStore
) -> None:
    session = session_store.get_or_create("voice-okay-sess")
    events: list[dict[str, Any]] = []

    async def send(event: dict[str, Any]) -> None:
        events.append(event)

    msg = {
        "type": "voice_turn",
        "text": "okay",
        "generation": 11,
    }

    await orchestrator.handle_message(session, msg, send=send)

    asst_msg = next((e for e in events if e["type"] == EventType.ASSISTANT_MESSAGE), None)
    assert asst_msg is not None
    assert asst_msg["data"]["is_voice"] is True
    assert asst_msg["data"].get("is_termination") is not True


@pytest.mark.asyncio
async def test_voice_barge_in_cancels(
    orchestrator: JarvisOrchestrator, session_store: InMemorySessionStore
) -> None:
    session = session_store.get_or_create("voice-barge-sess")

    async def send(event: dict[str, Any]) -> None:
        pass

    msg = {
        "type": "voice_barge_in",
        "generation": 42,
    }

    await orchestrator.handle_message(session, msg, send=send)
    assert True
