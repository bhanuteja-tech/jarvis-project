"""Matching orchestration: pre-indexed analyses, scoring, sort, summary.

The canonical ``jobs`` list and ``ranked_jobs`` are never modified; results
reference jobs by index. Sorting key (deterministic):
    (-score, -skills_required.points, -experience.points, job_index)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.matching.models import MatchingSummary, MatchResult
from app.matching.scorer import score_pair
from app.matching.views import build_candidate_view, build_job_view

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchingOutcome:
    match_results: list[MatchResult]
    summary: MatchingSummary
    #: Set when matching could not run (unusable candidate input).
    skipped_reason: str | None = None


def match_jobs(
    candidate_result: Mapping[str, Any] | None,
    jobs: Sequence[Mapping[str, Any]],
    ranked_jobs: Sequence[Mapping[str, Any]] | None = None,
    jd_analyses: Sequence[Mapping[str, Any]] | None = None,
) -> MatchingOutcome:
    candidate_view = build_candidate_view(candidate_result)
    if not candidate_view.usable:
        return MatchingOutcome(
            match_results=[],
            summary=MatchingSummary(
                evaluated=0, tiers={"strong": 0, "moderate": 0, "weak": 0}, jobs_without_analysis=0
            ),
            skipped_reason="candidate_profile_unusable",
        )

    analyses_by_index: dict[int, Mapping[str, Any]] = {}
    if jd_analyses:
        for entry in jd_analyses:
            if not isinstance(entry, Mapping):
                continue
            index_value = entry.get("job_index")
            if isinstance(index_value, int) and 0 <= index_value < len(jobs):
                analyses_by_index.setdefault(index_value, entry)

    jobs_without_analysis = sum(
        1
        for index in range(len(jobs))
        if index not in analyses_by_index or analyses_by_index[index].get("analysis") is None
    )

    scored: list[tuple[int, Any]] = []
    tiers = {"strong": 0, "moderate": 0, "weak": 0}

    for index, job in enumerate(jobs):
        job_view = build_job_view(job, index, analyses_by_index.get(index))
        result = score_pair(candidate_view, job_view)
        tiers[result["tier"]] += 1

        matched_required_component = result["breakdown"]["skills_required"]
        matched_names = sorted(job_view.required_skills & candidate_view.skill_names)
        missing_required = sorted(job_view.required_skills - candidate_view.skill_names)
        preferred_matched = sorted(job_view.preferred_skills & candidate_view.skill_names)
        matched_all = sorted(set(matched_names) | set(preferred_matched))

        gaps: list[str] = []
        warnings: list[str] = []
        if not job_view.has_analysis:
            gaps.append("jd_analysis_missing")
            warnings.append("JD analysis unavailable; canonical job fallback used")
        experience_component = result["breakdown"]["experience"]
        if "exceeds stated range" in experience_component.reason:
            warnings.append("overqualified_experience")

        match_result = MatchResult(
            job_index=index,
            score=result["total"],
            tier=result["tier"],
            confidence=result["confidence"],
            breakdown=result["breakdown"],
            matched_skills=matched_all,
            missing_required=missing_required,
            gaps=gaps,
            warnings=[
                *warnings,
                *([f"{len(gaps)} evidence gap(s)"] if gaps else []),
            ],
        )
        scored.append(
            (
                index,
                {
                    "result": match_result,
                    "skills_points": matched_required_component.points,
                    "experience_points": result["breakdown"]["experience"].points,
                },
            )
        )

    scored.sort(
        key=lambda item: (
            -item[1]["result"].score,
            -item[1]["skills_points"],
            -item[1]["experience_points"],
            item[0],
        )
    )

    ranked_results = [payload["result"] for _, payload in scored]
    summary = MatchingSummary(
        evaluated=len(jobs),
        tiers=tiers,
        jobs_without_analysis=jobs_without_analysis,
    )
    logger.info(
        "matching complete",
        extra={
            "source": "matching",
            "operation": "match_jobs",
            "jobs_evaluated": len(jobs),
            "tiers": dict(tiers),
            "jobs_without_analysis": jobs_without_analysis,
        },
    )
    return MatchingOutcome(
        match_results=ranked_results,
        summary=summary,
        skipped_reason=None,
    )


__all__ = ["MatchingOutcome", "match_jobs"]
