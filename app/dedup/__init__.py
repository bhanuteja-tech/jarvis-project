"""Cross-source job deduplication (Phase 1 Step 5, Option B).

In-memory canonical clustering before persistence:
- deterministic normalization (:mod:`app.dedup.normalize`)
- URL comparison keys built on the frozen career canonicalizer
  (:mod:`app.dedup.url_key`)
- rules R1-R3 with false-positive guards V1-V5 (:mod:`app.dedup.matcher`)
- Union-Find clustering, deterministic canonical-record selection, and
  provenance preservation (:mod:`app.dedup.cluster`)

Zero database schema changes; zero external services; stdlib only.
"""

from __future__ import annotations

from app.dedup.cluster import DedupOutcome, dedupe_jobs
from app.dedup.matcher import Decision, JobView, decide, make_view
from app.dedup.normalize import (
    is_remote_location,
    location_key,
    normalize_company,
    normalize_title,
)
from app.dedup.url_key import job_url_key

__all__ = [
    "Decision",
    "DedupOutcome",
    "JobView",
    "decide",
    "dedupe_jobs",
    "is_remote_location",
    "job_url_key",
    "location_key",
    "make_view",
    "normalize_company",
    "normalize_title",
]
