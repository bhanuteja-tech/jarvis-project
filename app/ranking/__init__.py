"""Deterministic job relevance & ranking (Phase 1 Step 6).

Layered design:
- preferences.py  : structured hard/soft user requirements (Pydantic)
- features.py     : verified-field feature extraction + skill matching
- filters.py      : hard requirement elimination (missing data never rejects)
- scorer.py       : transparent 0-100 additive scoring with breakdowns
- explain.py      : RankedJob / RankingSummary result shapes
- service.py      : orchestration facade used by the LangGraph node

No LLM. No embeddings. No timestamps manufactured from display text.
``source_created_at`` is the ONLY posting-freshness signal; missing values
yield explicitly-labeled neutral scores.
"""

from __future__ import annotations

from app.ranking.explain import RankedJob, RankingSummary
from app.ranking.preferences import (
    EmploymentType,
    ExperienceLevel,
    HardRequirements,
    SearchPreferences,
    SoftPreferences,
)
from app.ranking.service import rank_jobs

__all__ = [
    "EmploymentType",
    "ExperienceLevel",
    "HardRequirements",
    "RankedJob",
    "RankingSummary",
    "SearchPreferences",
    "SoftPreferences",
    "rank_jobs",
]
