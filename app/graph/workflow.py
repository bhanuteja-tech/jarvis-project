"""Minimal LangGraph orchestration foundation (Phase 1, Step 1).

One node: `fetch_sources`. It iterates registered source adapters through
the shared `SourceAdapter` contract, merges canonical results into state,
and converts failures into structured error records. It never raises across
the graph boundary and never silently drops a failure.

Deliberately absent: LLM calls, agents, conditional routing, persistence
nodes. These arrive with later steps/phases.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langgraph.graph import END, START, StateGraph

from app.graph.state import ErrorRecord, GraphState, WarningRecord
from app.sources.base import SourceAdapter
from app.sources.errors import SourceError

logger = logging.getLogger(__name__)

FETCH_SOURCES_NODE = "fetch_sources"


def _error_record_from_exception(adapter: SourceAdapter, exc: BaseException) -> ErrorRecord:
    if isinstance(exc, SourceError):
        record = exc.to_record()
        return ErrorRecord(
            source=record["source"],
            kind=record["kind"],
            retryable=record["retryable"],
            message=record["message"],
            endpoint=record["endpoint"],
            attempts=record["attempts"],
            status_code=record["status_code"],
        )
    return ErrorRecord(
        source=getattr(adapter, "source_name", "unknown"),
        kind=type(exc).__name__,
        retryable=False,
        message=f"unexpected adapter failure: {exc}",
        endpoint=None,
        attempts=0,
        status_code=None,
    )


def _make_fetch_sources_node(adapters: Sequence[SourceAdapter]):
    async def fetch_sources(state: GraphState) -> dict:
        preferences = state.get("search_preferences") or {}
        jobs: list[dict] = []
        errors: list[ErrorRecord] = []
        warnings: list[WarningRecord] = []
        discovered_urls: set[str] = set()

        for adapter in adapters:
            try:
                result = await adapter.fetch_jobs(preferences)
            except Exception as exc:
                logger.exception(
                    "source adapter failed",
                    extra={"source": getattr(adapter, "source_name", "unknown")},
                )
                errors.append(_error_record_from_exception(adapter, exc))
                continue

            jobs.extend(job.model_dump(mode="json") for job in result.jobs)
            warnings.extend(
                WarningRecord(source=w.source, code=w.code, message=w.message)
                for w in result.warnings
            )
            errors.extend(
                ErrorRecord(
                    source=record["source"],
                    kind=record["kind"],
                    retryable=record["retryable"],
                    message=record["message"],
                    endpoint=record["endpoint"],
                    attempts=record["attempts"],
                    status_code=record["status_code"],
                )
                for record in (error.to_record() for error in result.errors)
            )
            for job in result.jobs:
                if job.job_url:
                    discovered_urls.add(job.job_url)

        return {
            "jobs": jobs,
            "errors": errors,
            "warnings": warnings,
            "discovered_urls": sorted(discovered_urls),
        }

    return fetch_sources


def build_workflow(adapters: Sequence[SourceAdapter]):
    """Compile the Phase-1 discovery graph around the given adapters."""
    fetch_sources = _make_fetch_sources_node(adapters)

    builder = StateGraph(GraphState)
    builder.add_node(FETCH_SOURCES_NODE, fetch_sources)
    builder.add_edge(START, FETCH_SOURCES_NODE)
    builder.add_edge(FETCH_SOURCES_NODE, END)
    return builder.compile()


__all__ = ["FETCH_SOURCES_NODE", "build_workflow"]
