"""Matching result shapes (mirrors the ranking explainability contract)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TIER_THRESHOLDS: dict[str, int] = {"strong": 75, "moderate": 50}


def tier_for(score: float) -> str:
    if score >= TIER_THRESHOLDS["strong"]:
        return "strong"
    if score >= TIER_THRESHOLDS["moderate"]:
        return "moderate"
    return "weak"


@dataclass(frozen=True)
class ComponentResult:
    component: str
    points: float
    max: float
    status: str  # matched | partial | mismatch | neutral | not_requested
    reason: str


@dataclass(frozen=True)
class MatchResult:
    job_index: int
    score: float
    tier: str
    confidence: str  # high | medium | low
    breakdown: dict[str, Any]
    matched_skills: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_index": self.job_index,
            "score": self.score,
            "tier": self.tier,
            "confidence": self.confidence,
            "breakdown": {
                key: _serialize(value) for key, value in self.breakdown.items()
            },
            "matched_skills": list(self.matched_skills),
            "missing_required": list(self.missing_required),
            "gaps": list(self.gaps),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MatchingSummary:
    evaluated: int
    tiers: dict[str, int]
    jobs_without_analysis: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "tiers": dict(self.tiers),
            "jobs_without_analysis": self.jobs_without_analysis,
        }


def _serialize(value: Any) -> Any:
    if hasattr(value, "__dict__") and not isinstance(
        value, (dict, list, tuple, str, int, float, bool)
    ):
        return {key: _serialize(item) for key, item in vars(value).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


__all__ = ["ComponentResult", "MatchResult", "MatchingSummary", "tier_for"]
