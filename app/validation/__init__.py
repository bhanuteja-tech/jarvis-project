"""Phase 6 — Truthfulness + ATS Validation.

Read-only validation of the Phase-5 ``TailoredResume`` artifact:

    tailored_resume + candidate_profile + jd_analyses + match_results + jobs
        -> resolver -> truth checks (T1-T10) -> ats checks (A1-A8)
        -> ValidationReport

Severity contract:
- Truthfulness failures (T-series) => overall FAIL.
- ATS compatibility findings (A-series) => at most overall WARN.
- Every check is explainable and evidence-backed; missing data yields
  labeled neutrals/gaps, never invented facts.
- PII findings report counts only — never captured values.

Fail-open node; zero dependencies beyond frozen read-only imports;
100% deterministic; no LLM.
"""

from __future__ import annotations

from app.validation.models import (
    AtsSection,
    CheckResult,
    TruthSection,
    ValidationReport,
)
from app.validation.service import validate_resume

__all__ = [
    "AtsSection",
    "CheckResult",
    "TruthSection",
    "ValidationReport",
    "validate_resume",
]
