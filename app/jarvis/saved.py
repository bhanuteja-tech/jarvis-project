"""Session-scoped saved jobs + applications workspace data.

In-memory by design (matches every other Phase 7+ structure). A saved job is
a SAFE SNAPSHOT of the canonical Job at save time — title/company/location/
url/source plus the job_key identity — never the full JD body, never PII.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any


class SavedJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, list[dict[str, Any]]] = {}

    def _bucket(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._data.setdefault(session_id, [])

    def add(self, session_id: str, snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
        job_key = str(snapshot.get("job_key") or "")
        if not job_key:
            return None
        with self._lock:
            bucket = self._data.setdefault(session_id, [])
            if any(j["job_key"] == job_key for j in bucket):
                return None  # already saved; not an error
            entry = {
                "job_key": job_key,
                "__index": snapshot.get("__index"),
                "title": snapshot.get("title"),
                "company": snapshot.get("company"),
                "location": snapshot.get("location"),
                "job_url": snapshot.get("job_url"),
                "source": snapshot.get("source"),
                "score": snapshot.get("score"),
                "tier": snapshot.get("tier"),
                "status": "saved",
            }
            bucket.insert(0, entry)
            return entry

    def remove(self, session_id: str, job_key: str) -> bool:
        with self._lock:
            bucket = self._data.get(session_id, [])
            for i, entry in enumerate(bucket):
                if entry["job_key"] == job_key:
                    bucket.pop(i)
                    return True
            return False

    def list(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(entry) for entry in self._data.get(session_id, [])]

    def set_status(self, session_id: str, job_key: str, status: str) -> bool:
        allowed = {"saved", "applied", "interviewing", "rejected", "archived"}
        if status not in allowed:
            return False
        with self._lock:
            for entry in self._data.get(session_id, []):
                if entry["job_key"] == job_key:
                    entry["status"] = status
                    return True
            return False


saved_job_store = SavedJobStore()

__all__ = ["SavedJobStore", "saved_job_store"]
