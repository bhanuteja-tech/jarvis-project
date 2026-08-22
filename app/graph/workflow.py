"""Minimal LangGraph orchestration foundation.

Nodes:
- `fetch_sources`: iterates registered source adapters through the shared
  `SourceAdapter` contract, merges canonical results into state, and converts
  failures into structured error records. It never raises across the graph
  boundary and never silently drops a failure.
- `deduplicate_jobs` (Phase 1 Step 5): fail-open in-memory cross-source
  clustering over `state.jobs`. On any unexpected exception the original
  unmerged jobs pass through untouched and a non-retryable error record is
  appended — deduplication can never turn jobs into an empty result.

Deliberately absent: LLM calls, agents, conditional routing, persistence
nodes. These arrive with later steps/phases.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langgraph.graph import END, START, StateGraph

from app.config.settings import get_settings
from app.dedup.cluster import dedupe_jobs
from app.graph.state import ErrorRecord, GraphState, WarningRecord
from app.jdunderstanding.analyzer import build_analyzer
from app.ranking.service import rank_jobs
from app.sources.base import SourceAdapter
from app.sources.errors import SourceError

logger = logging.getLogger(__name__)

FETCH_SOURCES_NODE = "fetch_sources"
DEDUP_NODE = "deduplicate_jobs"
RANK_NODE = "rank_jobs"
JD_NODE = "analyze_jd"


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


async def _deduplicate_jobs(state: GraphState) -> dict:
    """Fail-open cross-source clustering (Step 5)."""
    jobs = state.get("jobs") or []
    try:
        outcome = dedupe_jobs(jobs)
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        logger.exception(
            "dedup failed; passing original jobs through unmerged",
            extra={"source": "dedup", "operation": "deduplicate_jobs"},
        )
        error = ErrorRecord(
            source="dedup",
            kind=type(exc).__name__,
            retryable=False,
            message=f"unexpected dedup failure; original jobs preserved: {exc}",
            endpoint=None,
            attempts=0,
            status_code=None,
        )
        warnings = list(state.get("warnings") or [])
        warnings.append(
            WarningRecord(
                source="dedup",
                code="dedup_failed",
                message=f"dedup failed; jobs passed through unmerged ({exc})",
            )
        )
        return {
            "errors": [*(state.get("errors") or []), error],
            "warnings": warnings,
        }

    new_warnings = [
        WarningRecord(source="dedup", code=item["code"], message=item["message"])
        for item in outcome.warnings
    ]
    return {
        "jobs": outcome.jobs,
        "warnings": [*(state.get("warnings") or []), *new_warnings],
    }


async def _rank_jobs(state: GraphState) -> dict:
    """Fail-open deterministic ranking (Step 6)."""
    jobs = state.get("jobs") or []
    preferences_raw = (state.get("search_preferences") or {}).get("ranking")
    try:
        outcome = rank_jobs(jobs, preferences_raw)
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        logger.exception(
            "ranking failed; jobs preserved unranked",
            extra={"source": "ranking", "operation": "rank_jobs"},
        )
        error = ErrorRecord(
            source="ranking",
            kind=type(exc).__name__,
            retryable=False,
            message=f"unexpected ranking failure; jobs preserved: {exc}",
            endpoint=None,
            attempts=0,
            status_code=None,
        )
        warnings = list(state.get("warnings") or [])
        warnings.append(
            WarningRecord(
                source="ranking",
                code="ranking_failed",
                message=f"ranking failed; treat jobs as unranked ({exc})",
            )
        )
        return {
            "errors": [*(state.get("errors") or []), error],
            "warnings": warnings,
        }

    return {
        "ranked_jobs": [ranked.to_dict() for ranked in outcome.ranked_jobs],
        "ranking_summary": outcome.summary.to_dict(),
    }


async def _analyze_jd(state: GraphState) -> dict:
    """Fail-open Phase-2 JD understanding over the top-K ranked jobs."""
    jobs = state.get("jobs") or []
    ranked = state.get("ranked_jobs") or []
    try:
        analyzer = build_analyzer(get_settings())
        results = await analyzer.analyze_ranked(jobs, ranked)
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        logger.exception(
            "jd analysis failed; jobs preserved",
            extra={"source": "jd_analysis", "operation": "analyze_jd"},
        )
        error = ErrorRecord(
            source="jd_analysis",
            kind=type(exc).__name__,
            retryable=False,
            message=f"unexpected jd analysis failure; jobs preserved: {exc}",
            endpoint=None,
            attempts=0,
            status_code=None,
        )
        warnings = list(state.get("warnings") or [])
        warnings.append(
            WarningRecord(
                source="jd_analysis",
                code="jd_analysis_failed",
                message=f"jd analysis failed; analyses unavailable ({exc})",
            )
        )
        return {
            "errors": [*(state.get("errors") or []), error],
            "warnings": warnings,
        }

    return {
        "jd_analyses": [result.model_dump() for result in results],
    }


def build_workflow(adapters: Sequence[SourceAdapter]):
    """Compile the Phase-1/2 discovery graph around the given adapters."""
    fetch_sources = _make_fetch_sources_node(adapters)

    builder = StateGraph(GraphState)
    builder.add_node(FETCH_SOURCES_NODE, fetch_sources)
    builder.add_node(DEDUP_NODE, _deduplicate_jobs)
    builder.add_node(RANK_NODE, _rank_jobs)
    builder.add_node(JD_NODE, _analyze_jd)
    builder.add_edge(START, FETCH_SOURCES_NODE)
    builder.add_edge(FETCH_SOURCES_NODE, DEDUP_NODE)
    builder.add_edge(DEDUP_NODE, RANK_NODE)
    builder.add_edge(RANK_NODE, JD_NODE)
    builder.add_edge(JD_NODE, END)
    return builder.compile()


__all__ = ["DEDUP_NODE", "FETCH_SOURCES_NODE", "JD_NODE", "RANK_NODE", "build_workflow"]
