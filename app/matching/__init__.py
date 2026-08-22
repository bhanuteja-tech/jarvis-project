"""Phase 4 — Candidate ↔ Job Matching.

Deterministic, explainable fit evaluation between the built
``CandidateProfile`` and every deduplicated canonical job:

    candidate_profile + jd_analyses + jobs (+ ranked_jobs cross-ref)
        -> views -> scorer -> match_results / matching_summary

Rules:
- soft-only matching (no hard filters, no elimination); tiers classify.
- weights are fixed: required 30 / preferred 10 / experience 20 /
  location 12 / employment 10 / education 8 / level 5 / salary 5.
- missing data yields labeled NEUTRAL partials — never positive evidence,
  never rejection.
- jobs without a JD analysis score via canonical fallback fields and carry
  the explicit ``jd_analysis_missing`` gap.
- fail-open node; PII never read; zero dependencies; no DB changes.
"""

from __future__ import annotations

from app.matching.models import ComponentResult, MatchResult, MatchingSummary
from app.matching.service import MatchingOutcome, match_jobs

__all__ = [
    "ComponentResult",
    "MatchResult",
    "MatchingOutcome",
    "MatchingSummary",
    "match_jobs",
]
