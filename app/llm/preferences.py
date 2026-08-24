"""Session-scoped LLM routing preferences (Phase 11).

Small in-memory store keyed by the existing Jarvis ``session_id``. No
database, no persistence — restarts forget, matching every other Phase 7+
in-memory structure.

Validation lives here so both the API layer and tests share one truth:
- provider names must exist in the Phase 10B catalog (``KNOWN_PROVIDERS``)
- preferred/fallback must be CONFIGURED at save time
- fallback entries are de-duplicated and never include the preferred one
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.config.settings import Settings
from app.llm.catalog import KNOWN_PROVIDERS, configured_provider_names


class PreferenceValidationError(Exception):
    """Safe 4xx-worthy rejection. Message contains names only, never secrets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RoutingPreferences:
    routing_enabled: bool = False
    preferred_provider: str = ""
    fallback_providers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing_enabled": self.routing_enabled,
            "preferred_provider": self.preferred_provider,
            "fallback_providers": list(self.fallback_providers),
        }


_EMPTY = RoutingPreferences()


class PreferenceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, RoutingPreferences] = {}

    def get(self, session_id: str) -> RoutingPreferences:
        with self._lock:
            return self._data.get(session_id, _EMPTY)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)

    def save(
        self,
        session_id: str,
        *,
        settings: Settings,
        payload: dict[str, Any],
    ) -> RoutingPreferences:
        """Validate + persist one session's preferences. Raises typed 4xx."""
        if not isinstance(session_id, str) or not session_id.strip():
            raise PreferenceValidationError("missing_session", "session_id is required")
        if not isinstance(payload, dict):
            raise PreferenceValidationError("invalid_payload", "body must be a JSON object")

        unknown_keys = set(payload) - {
            "routing_enabled",
            "preferred_provider",
            "fallback_providers",
        }
        if unknown_keys:
            raise PreferenceValidationError(
                "unknown_field", f"unsupported fields: {', '.join(sorted(unknown_keys))}"
            )

        known = KNOWN_PROVIDERS
        configured = set(configured_provider_names(settings))

        routing_enabled = bool(payload.get("routing_enabled", False))

        raw_preferred = payload.get("preferred_provider") or ""
        if not isinstance(raw_preferred, str):
            raise PreferenceValidationError(
                "unknown_provider", "preferred_provider must be a string"
            )
        preferred = raw_preferred.strip().lower()
        if preferred:
            if preferred not in known:
                raise PreferenceValidationError(
                    "unknown_provider", f"provider {preferred!r} is not supported"
                )
            if preferred not in configured:
                raise PreferenceValidationError(
                    "unconfigured_provider",
                    f"provider {preferred!r} is not configured on this server",
                )

        raw_fallback = payload.get("fallback_providers")
        if raw_fallback is None:
            raw_fallback = []
        if not isinstance(raw_fallback, list) or len(raw_fallback) > 6:
            raise PreferenceValidationError(
                "invalid_fallbacks", "fallback_providers must be a list of at most 6 names"
            )
        fallback: list[str] = []
        for entry in raw_fallback:
            if not isinstance(entry, str):
                raise PreferenceValidationError(
                    "unknown_provider", "fallback entries must be strings"
                )
            name = entry.strip().lower()
            if not name:
                continue
            if name not in known:
                raise PreferenceValidationError(
                    "unknown_provider", f"provider {name!r} is not supported"
                )
            if name not in configured:
                raise PreferenceValidationError(
                    "unconfigured_provider",
                    f"provider {name!r} is not configured on this server",
                )
            if name == preferred or name in fallback:
                continue
            fallback.append(name)

        prefs = RoutingPreferences(
            routing_enabled=routing_enabled,
            preferred_provider=preferred,
            fallback_providers=tuple(fallback),
        )
        with self._lock:
            self._data[session_id] = prefs
        return prefs


#: Process-wide store used by the API layer and the orchestrator.
preference_store = PreferenceStore()


__all__ = [
    "PreferenceStore",
    "PreferenceValidationError",
    "RoutingPreferences",
    "preference_store",
]
