"""SearchApi source adapter package.

Two capabilities under one provider, deliberately kept schema-separated:
- ``GoogleJobsAdapter``   -> canonical Jobs   (engine=google_jobs)
- ``GoogleSearchAdapter`` -> discovery candidate URLs (engine=google), NOT jobs
"""

from __future__ import annotations

from app.sources.searchapi.candidates import (
    GoogleSearchAdapter,
    SearchCandidateResult,
    SearchCandidatesResult,
)
from app.sources.searchapi.client import ENGINES, SearchApiClient, validate_engine
from app.sources.searchapi.jobs_adapter import (
    ALLOWED_JOB_PARAMS,
    DEFAULT_MAX_PAGES,
    GoogleJobsAdapter,
    build_job_params,
    extract_htidocid,
    normalize_job,
    resolve_source_job_id,
)

__all__ = [
    "ALLOWED_JOB_PARAMS",
    "DEFAULT_MAX_PAGES",
    "ENGINES",
    "GoogleJobsAdapter",
    "GoogleSearchAdapter",
    "SearchApiClient",
    "SearchCandidateResult",
    "SearchCandidatesResult",
    "build_job_params",
    "extract_htidocid",
    "normalize_job",
    "resolve_source_job_id",
    "validate_engine",
]
