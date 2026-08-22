"""Shared contracts implemented by every job-source adapter.

A source adapter is the only component allowed to talk to its external
source. It retrieves data, validates it against the source's documented
schema, normalizes it into the canonical `Job` model, and returns everything
through `FetchResult`. Failures are expressed as typed `SourceError`s —
either raised (whole-request failure) or returned inside `FetchResult.errors`
(per-board / per-item failures that must not mask successful results).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.models.job import Job
from app.sources.errors import SourceError


@dataclass(frozen=True)
class SourceWarning:
    """A non-fatal problem observed while processing one part of a response."""

    source: str
    code: str
    message: str


@dataclass(frozen=True)
class FetchResult:
    jobs: tuple[Job, ...] = ()
    warnings: tuple[SourceWarning, ...] = ()
    errors: tuple[SourceError, ...] = ()
    #: Number of job items seen upstream before validation/normalization.
    raw_count: int = 0


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract every source adapter implements."""

    source_name: str

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        """Fetch jobs according to caller-supplied preferences.

        Implementations must never raise for expected upstream conditions;
        those belong in `FetchResult.errors`. Unexpected exceptions may
        propagate to the orchestration layer.
        """
        ...  # pragma: no cover


__all__ = [
    "FetchResult",
    "SourceAdapter",
    "SourceWarning",
]
