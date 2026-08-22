"""Canonical LangGraph state.

The state carries only source-agnostic structures:
- canonical jobs as plain dicts (produced via `Job.model_dump`),
- generic error/warning records produced by `SourceError.to_record`.

No Greenhouse-specific (or any source-specific) response structure may ever
appear here. `raw_jobs` is reserved for later Phase 1 steps; this step does
not populate it.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ErrorRecord(TypedDict):
    source: str
    kind: str
    retryable: bool
    message: str
    endpoint: str | None
    attempts: int
    status_code: int | None


class WarningRecord(TypedDict):
    source: str
    code: str
    message: str


class GraphState(TypedDict, total=False):
    user_query: str | None
    search_preferences: dict[str, Any]
    search_queries: list[str]
    discovered_urls: list[str]
    raw_jobs: list[dict[str, Any]]
    jobs: list[dict[str, Any]]
    errors: list[ErrorRecord]
    warnings: list[WarningRecord]
    # Phase 1 Step 6 (additive): ranking output wrappers reference jobs by
    # index; the canonical `jobs` list itself is never reordered or modified.
    ranked_jobs: list[dict[str, Any]]
    ranking_summary: dict[str, Any]
    # Phase 2 (additive): per-job JD analyses + analysis failure records.
    jd_analyses: list[dict[str, Any]]
    analysis_errors: list[dict[str, Any]]
    # Phase 3 (additive): candidate branch. `candidate_input` is user-supplied
    # ({text} | {structured}); `candidate_profile` is the built CandidateResult.
    candidate_input: dict[str, Any]
    candidate_profile: dict[str, Any]


__all__ = ["ErrorRecord", "GraphState", "WarningRecord"]
