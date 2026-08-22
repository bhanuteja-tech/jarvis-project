"""Ranked-result shapes: wrappers around state.jobs — the Job model itself
is never modified."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RankedJob:
    job_index: int
    score: float
    breakdown: dict[str, Any]
    matched_skills: tuple[str, ...]
    missing_required_skills: tuple[str, ...]
    hard_gaps: tuple[str, ...]
    freshness: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_index": self.job_index,
            "score": self.score,
            "breakdown": _serialize(self.breakdown),
            "matched_skills": list(self.matched_skills),
            "missing_required_skills": list(self.missing_required_skills),
            "hard_gaps": list(self.hard_gaps),
            "freshness": dict(self.freshness),
        }


@dataclass(frozen=True)
class RankingSummary:
    kept: int
    filtered_out: int
    rejected_histogram: dict[str, int]
    limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": self.kept,
            "filtered_out": self.filtered_out,
            "rejected_histogram": dict(self.rejected_histogram),
            "limit": self.limit,
        }


def _serialize(value: Any) -> Any:
    if hasattr(value, "__dict__") and not isinstance(value, (dict, list, str, int, float, bool)):
        return {
            key: _serialize(item) for key, item in vars(value).items()
        }
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


__all__ = ["RankedJob", "RankingSummary"]
