"""GoogleJobsAdapter: engine=google_jobs -> validate -> normalize -> Jobs.

Approved correction enforced structurally: ``time_period`` is documented for
the ``google`` engine ONLY. This adapter emits exactly {q, gl, hl, location}
(plus the internally-managed ``next_page_token``); any other preference keys
— including ``time_period`` — are dropped and reported via a warning.

Timestamp policy (per lock):
- ``source_created_at`` stays None: upstream provides no absolute timestamp.
- ``detected_extensions.posted_at`` ("1 day ago") is preserved verbatim in
  ``extra.posted_at_display`` and NEVER converted into a datetime.
- ``discovered_at``/``fetched_at`` remain internal UTC timestamps.

Identity strategy (approved):
- primary: ``gj:<htidocid>`` extracted from the documented sharing_link;
- fallback: deterministic ``derived:<uuid5(company|title|location)>`` — no
  randomness, no clock involvement.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from app.models.job import Job
from app.sources.base import FetchResult, SourceWarning
from app.sources.errors import (
    SourceError,
    SourceValidationError,
)
from app.sources.searchapi.client import SOURCE_NAME, SearchApiClient
from app.sources.searchapi.schemas import GoogleJobsJob, GoogleJobsResponse

logger = logging.getLogger(__name__)

_PREFERENCES_KEY = "searchapi"
_JOBS_KEY = "google_jobs"

#: The ONLY request parameters this adapter may emit for google_jobs.
ALLOWED_JOB_PARAMS: frozenset[str] = frozenset({"gl", "hl", "location"})

DEFAULT_MAX_PAGES = 5

_IDENTITY_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://www.searchapi.io/api/v1/search#google_jobs"
)


def _blank_to_none(value: Any) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def extract_htidocid(sharing_link: str | None) -> str | None:
    """Extract Google's posting doc id from a sharing_link's query string."""
    if not sharing_link:
        return None
    try:
        values = parse_qs(urlsplit(str(sharing_link)).query).get("htidocid")
    except ValueError:
        return None
    if not values:
        return None
    return values[0].strip() or None


def derive_fallback_id(*, company_name: str | None, title: str | None, location: str | None) -> str:
    """Deterministic content identity: stable across identical searches."""
    material = "|".join(
        (
            (company_name or "").strip(),
            (title or "").strip(),
            (location or "").strip(),
        )
    )
    return f"derived:{uuid.uuid5(_IDENTITY_NAMESPACE, material)}"


def resolve_source_job_id(job: GoogleJobsJob) -> tuple[str, str]:
    """Return ``(source_job_id, identity_source)`` per the approved strategy."""
    htidocid = extract_htidocid(str(job.sharing_link) if job.sharing_link else None)
    if htidocid:
        return f"gj:{htidocid}", "htidocid"
    return (
        derive_fallback_id(company_name=job.company_name, title=job.title, location=job.location),
        "derived",
    )


def build_job_params(
    preferences: Mapping[str, Any],
) -> tuple[dict[str, str], list[str]]:
    """Build whitelisted google_jobs request parameters.

    Returns ``(params, ignored_keys)``; ``params`` is empty when no usable
    ``q`` was supplied.
    """
    source_prefs = preferences.get(_PREFERENCES_KEY)
    jobs_prefs = source_prefs.get(_JOBS_KEY) if isinstance(source_prefs, Mapping) else None
    if not isinstance(jobs_prefs, Mapping):
        return {}, []

    raw_q = jobs_prefs.get("q")
    if not isinstance(raw_q, str) or not raw_q.strip():
        return {}, []

    params = {"q": raw_q.strip()}
    ignored: list[str] = []
    for key, value in jobs_prefs.items():
        if not isinstance(key, str) or key == "q":
            continue
        if key in ALLOWED_JOB_PARAMS and isinstance(value, str) and value.strip():
            params[key] = value.strip()
        else:
            ignored.append(key)
    return params, sorted(set(ignored))


def normalize_job(job: GoogleJobsJob, *, query: str) -> Job:
    """Convert one validated Google Jobs result into a canonical ``Job``."""
    source_job_id, identity_source = resolve_source_job_id(job)
    detected = job.detected_extensions or {}

    schedule = detected.get("schedule")
    employment_type = _blank_to_none(schedule) if isinstance(schedule, str) else None
    posted_at = detected.get("posted_at")

    extra = {
        "engine": "google_jobs",
        "query": query,
        "position": job.position,
        "via": _blank_to_none(job.via),
        # Relative display text only; deliberately never parsed as a datetime.
        "posted_at_display": posted_at if isinstance(posted_at, str) else None,
        "extensions": job.extensions,
        "detected_extensions": job.detected_extensions,
        "job_highlights": (
            [item.model_dump() for item in job.job_highlights] if job.job_highlights else None
        ),
        "apply_links": (
            [item.model_dump() for item in job.apply_links] if job.apply_links else None
        ),
        "identity_source": identity_source,
    }

    return Job(
        source=SOURCE_NAME,
        source_job_id=source_job_id,
        title=(job.title or "").strip(),
        company=_blank_to_none(job.company_name),
        location=_blank_to_none(job.location),
        description=job.description if job.description else None,
        requirements=None,
        responsibilities=None,
        employment_type=employment_type,
        # No structured salary field exists in the documented contract.
        salary=None,
        job_url=str(job.sharing_link) if job.sharing_link else None,
        apply_url=str(job.apply_link) if job.apply_link else None,
        # No trustworthy absolute upstream timestamp exists.
        source_created_at=None,
        source_updated_at=None,
        extra=extra,
    )


class GoogleJobsAdapter:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: SearchApiClient,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._client = client
        self._max_pages = max_pages

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        """Search google_jobs per ``preferences["searchapi"]["google_jobs"]``."""
        params, ignored = build_job_params(preferences)
        warnings: list[SourceWarning] = []

        if not params:
            return FetchResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="no_query_requested",
                        message="no searchapi.google_jobs.q present in preferences",
                    ),
                )
            )

        if ignored:
            warnings.append(
                SourceWarning(
                    source=self.source_name,
                    code="unsupported_parameters_ignored",
                    message=(
                        "parameters not documented for google_jobs were ignored: "
                        f"{', '.join(ignored)}"
                    ),
                )
            )

        query = params["q"]
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        seen_tokens: set[str] = set()
        raw_count = 0
        pages = 0
        token: str | None = None
        errors: list[SourceError] = []

        while True:
            request_params = dict(params)
            if token:
                request_params["next_page_token"] = token

            payload = await self._client.search("google_jobs", request_params)

            try:
                response = GoogleJobsResponse.model_validate(payload)
            except ValidationError as exc:
                raise SourceValidationError(
                    "response does not match the documented google_jobs schema",
                    source=self.source_name,
                    endpoint="google_jobs",
                    cause=exc,
                ) from exc

            pages += 1
            raw_count += len(response.jobs)

            for job_item in response.jobs:
                try:
                    job = normalize_job(job_item, query=query)
                except SourceError:
                    raise
                except Exception as exc:
                    identifier = (
                        f"gj:{extract_htidocid(str(job_item.sharing_link))}"
                        if job_item.sharing_link
                        else f"position={job_item.position}"
                    )
                    warnings.append(
                        SourceWarning(
                            source=self.source_name,
                            code="normalization_failed",
                            message=(
                                f"skipped google_jobs item ({identifier}) during "
                                f"normalization: {type(exc).__name__}: {exc}"
                            ),
                        )
                    )
                    continue

                if job.source_job_id in seen_ids:
                    warnings.append(
                        SourceWarning(
                            source=self.source_name,
                            code="duplicate_skipped",
                            message=(
                                f"posting id={job.source_job_id} already collected "
                                "during this traversal; duplicate skipped"
                            ),
                        )
                    )
                    continue
                seen_ids.add(job.source_job_id)
                jobs.append(job)

            next_token = (
                response.pagination.next_page_token.strip()
                if response.pagination is not None and response.pagination.next_page_token
                else None
            )
            if not next_token:
                break
            if next_token in seen_tokens:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="repeated_next_page_token",
                        message=(
                            "upstream returned an already-seen next_page_token; "
                            "stopping to prevent an infinite loop"
                        ),
                    )
                )
                break
            if pages >= self._max_pages:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="max_pages_reached",
                        message=(
                            f"stopped after {pages} pages (hard ceiling); further "
                            "pages were not fetched"
                        ),
                    )
                )
                break
            seen_tokens.add(next_token)
            token = next_token

        logger.info(
            "google_jobs adapter run complete",
            extra={
                "source": self.source_name,
                "operation": "fetch_jobs",
                "pages_fetched": pages,
                "raw_count": raw_count,
                "jobs_normalized": len(jobs),
                "items_skipped": sum(1 for w in warnings if w.code == "normalization_failed"),
            },
        )
        return FetchResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            errors=tuple(errors),
            raw_count=raw_count,
        )
