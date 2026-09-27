"""Redis-Backed Session Store with strict Persistence Split.

Implements the Step 3B Redis Persistence Specification:
- PERSISTED TO REDIS:
    * Metadata (session_id, user_id, domain, created_at)
    * ComputerState logical state (current_url, active_application, current_directory, etc.)
    * TypedContext domain entities (last_opened_folder, active video/playlist, etc.)
- RECONSTRUCTED FRESH ON RECONNECT:
    * OS and UI automation controllers (WindowController, ApplicationController, etc.)
    * BrowserManager, BrowserSessionManager
    * ActionCircuitBreaker counters
    * TaskManager generation and queue
    * User-scoped credential vault
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import redis

from app.computer.session_context import SessionContext, create_session_context
from app.config.settings import Settings, get_settings
from app.jarvis.sessions import (
    CareerSession,
    ComputerSession,
    Domain,
    InMemorySessionStore,
    Session,
)

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """Session store persisting serializable state to Redis while recreating OS handles."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        *,
        ttl_seconds: int = 86400,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ttl = ttl_seconds or self._settings.redis_session_ttl_seconds
        self._in_memory = InMemorySessionStore()

        if redis_client is not None:
            self._client: redis.Redis | None = redis_client
        else:
            try:
                self._client = redis.from_url(
                    self._settings.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                )
            except Exception as exc:
                logger.warning(
                    "Could not initialize Redis client from URL %s: %s",
                    self._settings.redis_url,
                    exc,
                )
                self._client = None

    def _key(self, session_id: str) -> str:
        return f"jarvis:session:{session_id}"

    def get(self, session_id: str) -> Session | None:
        """Fetch and reconstruct session from Redis or in-memory fallback."""
        if not session_id:
            return None

        # 1. Try Redis
        if self._client is not None:
            try:
                raw = self._client.get(self._key(session_id))
                if raw:
                    data = json.loads(raw)
                    return self._reconstruct_session(data)
            except Exception as exc:
                logger.warning(
                    "Redis get failed for session %s: %s. Falling back to memory.",
                    session_id,
                    exc,
                )

        # 2. Fall back to memory
        return self._in_memory._sessions.get(session_id)

    def save(self, session: Session) -> bool:
        """Persist session's logical state to Redis."""
        # Always maintain active in-memory cache
        self._in_memory._sessions[session.session_id] = session

        if self._client is None:
            return False

        try:
            payload: dict[str, Any] = {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "domain": session.domain,
                "created_at": session.created_at,
            }

            if isinstance(session, ComputerSession):
                ctx: SessionContext = session.session_context
                payload["persisted_state"] = ctx.get_persisted_state()

            serialized = json.dumps(payload)
            self._client.setex(self._key(session.session_id), self._ttl, serialized)
            return True
        except Exception as exc:
            logger.warning("Redis save failed for session %s: %s", session.session_id, exc)
            return False

    def get_or_create(
        self,
        session_id: str | None = None,
        *,
        user_id: str = "default",
        domain: Domain = "career",
        lock: bool = False,
    ) -> Session:
        """Retrieve existing session or create fresh one with persistence."""
        key = session_id or str(uuid4())

        # Check existing
        existing = self.get(key)
        if existing is not None:
            if lock:
                existing.lock_domain()
            return existing

        # Create new
        now_iso = datetime.now(UTC).isoformat()
        if domain == "computer":
            sess: Session = ComputerSession(
                session_id=key, user_id=user_id, created_at=now_iso, domain="computer"
            )
        else:
            sess = CareerSession(
                session_id=key, user_id=user_id, created_at=now_iso, domain="career"
            )

        if lock:
            sess.lock_domain()

        self.save(sess)
        return sess

    def delete(self, session_id: str) -> bool:
        """Delete session from Redis and memory."""
        self._in_memory._sessions.pop(session_id, None)
        if self._client is not None:
            try:
                self._client.delete(self._key(session_id))
                return True
            except Exception as exc:
                logger.warning("Redis delete failed for session %s: %s", session_id, exc)
        return False

    def _reconstruct_session(self, data: dict[str, Any]) -> Session:
        """Reconstruct session and fresh SessionContext from persisted data dict."""
        session_id = data["session_id"]
        user_id = data.get("user_id", "default")
        domain: Domain = data.get("domain", "career")
        created_at = data.get("created_at", datetime.now(UTC).isoformat())

        if domain == "computer":
            sess = ComputerSession(
                session_id=session_id,
                user_id=user_id,
                created_at=created_at,
                domain="computer",
            )
            persisted_state = data.get("persisted_state")
            if persisted_state:
                # Reconstruct fresh SessionContext restoring only logical fields
                ctx = create_session_context(
                    user_id=user_id,
                    session_id=session_id,
                    restored_logical_state=persisted_state,
                )
                sess.session_context = ctx
            return sess

        return CareerSession(
            session_id=session_id,
            user_id=user_id,
            created_at=created_at,
            domain="career",
        )
