"""Phase 5 — Resume Tailoring.

Deterministic v1 tailoring over structured evidence:

    candidate_profile + target match_result + target JDAnalysis (+ jobs echo)
        -> views -> selection/ordering rules -> TailoredResume
        -> truthfulness validation (token-subset guard)
        -> [optional semantic bullet rewriting behind TailoringLlmClient,
           disabled by default; unverifiable rewrites are rejected]

Core invariants:
- The original CandidateProfile is the sole source of candidate facts and is
  never modified.
- Every tailored fact carries evidence_refs pointing back to profile paths.
- Missing JD-required skills are surfaced in ``unaddressed_jd_requirements``
  and NEVER inserted.
- identity/contact (PII) are never copied into the tailored output.
"""

from __future__ import annotations

from app.tailoring.service import TailoringOutcome, tailor_resume
from app.tailoring.validator import (
    DisabledTailoringLlmClient,
    TailoringLlmClient,
    TruthinessValidator,
)
from app.tailoring.models import ChangeRecord, TailoredResume, TailoringResult

__all__ = [
    "ChangeRecord",
    "DisabledTailoringLlmClient",
    "TailoredResume",
    "TailoringLlmClient",
    "TailoringResult",
    "TailoringOutcome",
    "TruthinessValidator",
    "tailor_resume",
]
