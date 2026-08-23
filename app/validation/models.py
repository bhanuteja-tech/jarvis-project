"""Validation report shapes (mirrors the matching explainability contract)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # passed | warning | failed | info
    detail: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TruthSection:
    status: str  # PASS | FAIL
    checks: list[CheckResult] = field(default_factory=list)


@dataclass(frozen=True)
class KeywordCount:
    term: str
    original: int
    tailored: int


@dataclass(frozen=True)
class AtsMetrics:
    required_coverage_pct: float
    preferred_coverage_pct: float
    responsibility_token_coverage_pct: float
    keyword_counts: list[KeywordCount] = field(default_factory=list)


@dataclass(frozen=True)
class AtsSection:
    status: str  # PASS | WARN
    checks: list[CheckResult] = field(default_factory=list)
    metrics: AtsMetrics | None = None


@dataclass(frozen=True)
class ValidationReport:
    overall_status: str  # PASS | WARN | FAIL
    evaluated_job_index: int | None
    truth: TruthSection
    ats: AtsSection
    confidence: str  # high | medium | low
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "evaluated_job_index": self.evaluated_job_index,
            "truth": _serialize(self.truth),
            "ats": _serialize(self.ats),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "errors": [dict(error) for error in self.errors],
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


__all__ = [
    "AtsMetrics",
    "AtsSection",
    "CheckResult",
    "KeywordCount",
    "TruthSection",
    "ValidationReport",
]
