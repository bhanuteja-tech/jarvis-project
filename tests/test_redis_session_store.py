"""Tests for Redis-Backed Session Store with strict Persistence Split."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.jarvis.redis_store import RedisSessionStore
from app.jarvis.sessions import CareerSession, ComputerSession


class MockRedis:
    """In-memory dictionary simulating redis.Redis key-value store with TTL."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, time: int, value: str) -> bool:
        self.store[key] = value
        self.ttls[key] = time
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.ttls.pop(k, None)
                deleted += 1
        return deleted


class TestRedisSessionStore:
    """Verifies RedisSessionStore conforms to Step 3B Persistence Split."""

    def test_save_and_reconstruct_computer_session(self) -> None:
        mock_redis = MockRedis()
        store = RedisSessionStore(redis_client=mock_redis, ttl_seconds=3600)  # type: ignore[arg-type]

        # 1. Create and mutate session
        session = store.get_or_create("sess_test_123", user_id="alice", domain="computer")
        assert isinstance(session, ComputerSession)

        session.computer_state.update(
            current_url="https://github.com/my-project",
            active_application="visual_studio_code",
            current_directory="/home/alice/repo",
        )
        session.session_context.typed_context.set_youtube_entities([
            {
                "title": "Campus X Python Tutorial",
                "url": "https://youtube.com/watch?v=123",
                "channel": "CampusX",
            }
        ])
        session.session_context.typed_context.last_active_domain = "browser"

        # Save to Redis
        assert store.save(session) is True

        # Check raw stored JSON
        raw_json = mock_redis.get("jarvis:session:sess_test_123")
        assert raw_json is not None
        data = json.loads(raw_json)

        assert data["session_id"] == "sess_test_123"
        assert data["user_id"] == "alice"
        assert data["domain"] == "computer"
        assert mock_redis.ttls["jarvis:session:sess_test_123"] == 3600

        # Assert persisted logical state
        p_state = data["persisted_state"]
        assert p_state["computer_state"]["current_url"] == "https://github.com/my-project"
        assert p_state["computer_state"]["active_application"] == "visual_studio_code"
        assert p_state["computer_state"]["current_directory"] == "/home/alice/repo"
        assert len(p_state["typed_context"]["youtube_video_results"]) == 1
        assert p_state["typed_context"]["last_active_domain"] == "browser"

        # Assert physical OS handles are NOT in the stored payload
        assert "window_controller" not in p_state
        assert "browser_manager" not in p_state
        assert "app_controller" not in p_state

        # 2. Simulate fresh connection / new process: create new store instance with same Redis
        new_store = RedisSessionStore(redis_client=mock_redis)  # type: ignore[arg-type]
        restored = new_store.get("sess_test_123")

        assert isinstance(restored, ComputerSession)
        assert restored.session_id == "sess_test_123"
        assert restored.user_id == "alice"
        assert restored.computer_state.current_url == "https://github.com/my-project"
        assert restored.computer_state.active_application == "visual_studio_code"
        assert restored.computer_state.current_directory == "/home/alice/repo"

        # Assert typed_context restored with typed domain entities
        assert len(restored.session_context.typed_context.youtube_video_results) == 1
        video = restored.session_context.typed_context.youtube_video_results[0]
        assert video.title == "Campus X Python Tutorial"
        assert video.url == "https://youtube.com/watch?v=123"
        assert video.channel == "CampusX"
        assert restored.session_context.typed_context.last_active_domain == "browser"

        # Controllers must be reconstructed fresh (not None, but new instances)
        assert restored.session_context.window_controller is not None
        assert restored.session_context.browser_manager is not None
        orig_wc = session.session_context.window_controller
        assert restored.session_context.window_controller is not orig_wc

    def test_save_and_reconstruct_career_session(self) -> None:
        mock_redis = MockRedis()
        store = RedisSessionStore(redis_client=mock_redis)  # type: ignore[arg-type]

        session = store.get_or_create("career_sess_456", user_id="bob", domain="career")
        assert isinstance(session, CareerSession)
        assert store.save(session) is True

        # Reconstruct
        restored = store.get("career_sess_456")
        assert isinstance(restored, CareerSession)
        assert restored.session_id == "career_sess_456"
        assert restored.user_id == "bob"
        assert restored.domain == "career"

    def test_delete_removes_from_redis_and_memory(self) -> None:
        mock_redis = MockRedis()
        store = RedisSessionStore(redis_client=mock_redis)  # type: ignore[arg-type]

        store.get_or_create("to_delete", user_id="charlie", domain="computer")
        assert store.get("to_delete") is not None

        assert store.delete("to_delete") is True
        assert store.get("to_delete") is None
        assert mock_redis.get("jarvis:session:to_delete") is None

    def test_fallback_to_in_memory_when_redis_fails(self) -> None:
        broken_redis = MagicMock()
        broken_redis.get.side_effect = ConnectionError("Redis unreachable")
        broken_redis.setex.side_effect = ConnectionError("Redis unreachable")

        store = RedisSessionStore(redis_client=broken_redis)  # type: ignore[arg-type]
        session = store.get_or_create("fallback_sess", user_id="dan", domain="career")

        # Memory store maintains active session despite Redis exception
        assert session is not None
        assert store.get("fallback_sess") is not None
        assert store.get("fallback_sess").user_id == "dan"
