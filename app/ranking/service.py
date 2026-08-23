"""Ranking orchestration facade used by the LangGraph node.

Pipeline: extract features -> hard filters -> deterministic scoring ->
stable sort -> limit. The original jobs list is NEVER modified; ranked
wrappers reference jobs by index.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ranking.explain import RankedJob, RankingSummary
from app.ranking.features import extract_features
from app.ranking.filters import apply_hard_filters
from app.ranking.preferences import SearchPreferences
from app.ranking.scorer import score_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankingOutcome:
    ranked_jobs: list[RankedJob]
    summary: RankingSummary


def rank_jobs(
    jobs: list[Mapping[str, Any]],
    preferences_raw: Mapping[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> RankingOutcome:
    prefs = SearchPreferences.from_state(preferences_raw)
    histogram: Counter[str] = Counter()
    survivors: list[tuple[int, Any]] = []

    for index, job in enumerate(jobs):
        features = extract_features(job, index)
        outcome = apply_hard_filters(features, prefs.hard, now=now)
        if outcome.passed:
            scoring = score_job(features, prefs, now=now)
            survivors.append(
                (
                    index,
                    {
                        "features": features,
                        "scoring": scoring,
                        "gaps": outcome.gaps,
                    },
                )
            )
        else:
            histogram[outcome.failed_reason or "unknown"] += 1

    survivors.sort(key=lambda item: item[1]["scoring"].tie_key)

    ranked: list[RankedJob] = []
    for index, payload in survivors[: prefs.soft.limit]:
        scoring = payload["scoring"]
        freshness = {
            "evidence": ("source_created_at" if features_has_created(payload) else "unavailable"),
            "age_hours": _age_hours(payload["features"].created_at, now),
        }
        ranked.append(
            RankedJob(
                job_index=index,
                score=scoring.total,
                breakdown=scoring.breakdown,
                matched_skills=scoring.matched_skills,
                missing_required_skills=scoring.missing_required_skills,
                hard_gaps=payload["gaps"],
                freshness=freshness,
            )
        )

    summary = RankingSummary(
        kept=len(ranked),
        filtered_out=sum(histogram.values()),
        rejected_histogram=dict(histogram),
        limit=prefs.soft.limit,
    )

    logger.info(
        "ranking complete",
        extra={
            "source": "ranking",
            "operation": "rank_jobs",
            "input_records": len(jobs),
            "kept": summary.kept,
            "filtered_out": summary.filtered_out,
        },
    )
    return RankingOutcome(ranked_jobs=ranked, summary=summary)


def features_has_created(payload: dict[str, Any]) -> bool:
    return payload["features"].created_at is not None


def _age_hours(created_at: datetime | None, now: datetime | None) -> float | None:
    if created_at is None:
        return None
    reference = now or datetime.now().astimezone()
    return round(max(0.0, (reference - created_at).total_seconds() / 3600.0), 2)


__all__ = ["RankingOutcome", "rank_jobs"]
