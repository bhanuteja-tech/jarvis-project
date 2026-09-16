"""RapidApiAdapter: preferences -> RapidApiClient -> validate -> normalize -> canonical Jobs."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.models.job import Job, Salary
from app.sources.base import FetchResult, SourceWarning
from app.sources.errors import SourceError, SourceValidationError
from app.sources.rapidapi.client import SOURCE_NAME, RapidApiClient
from app.sources.rapidapi.schemas import RapidApiJob, RapidApiResponse

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 3


def _blank_to_none(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def normalize_job(job: RapidApiJob, *, query: str) -> Job:
    """Convert one validated RapidAPI job into a canonical Job model."""
    source_job_id = f"rapidapi:{job.job_id}"

    # Location construction
    loc_parts = [p for p in [job.job_city, job.job_state, job.job_country] if p and str(p).strip()]
    location = ", ".join(loc_parts) if loc_parts else None

    # Timestamp conversion (if epoch timestamp available)
    source_created_at: datetime | None = None
    if job.job_posted_at_timestamp:
        try:
            source_created_at = datetime.fromtimestamp(float(job.job_posted_at_timestamp), tz=UTC)
        except (ValueError, OSError, TypeError):
            source_created_at = None

    # Structured Salary
    salary_model: Salary | None = None
    if job.job_min_salary is not None or job.job_max_salary is not None:
        salary_model = Salary(
            min_amount=Decimal(str(job.job_min_salary)) if job.job_min_salary is not None else None,
            max_amount=Decimal(str(job.job_max_salary)) if job.job_max_salary is not None else None,
            currency=_blank_to_none(job.job_salary_currency),
            period=_blank_to_none(job.job_salary_period),
        )

    # Requirements string
    reqs_str: str | None = None
    if job.job_required_skills:
        reqs_str = ", ".join(s for s in job.job_required_skills if s and str(s).strip())

    extra: dict[str, Any] = {
        "engine": "rapidapi_jsearch",
        "query": query,
        "job_publisher": _blank_to_none(job.job_publisher),
        "job_is_remote": job.job_is_remote,
        "employer_logo": _blank_to_none(job.employer_logo),
        "employer_website": _blank_to_none(job.employer_website),
        "posted_at_datetime_utc": _blank_to_none(job.job_posted_at_datetime_utc),
    }

    return Job(
        source=SOURCE_NAME,
        source_job_id=source_job_id,
        title=(job.job_title or "Untitled Position").strip(),
        company=_blank_to_none(job.employer_name),
        location=location,
        description=_blank_to_none(job.job_description),
        requirements=reqs_str,
        responsibilities=None,
        employment_type=_blank_to_none(job.job_employment_type),
        salary=salary_model,
        job_url=_blank_to_none(job.job_apply_link),
        apply_url=_blank_to_none(job.job_apply_link),
        source_created_at=source_created_at,
        source_updated_at=None,
        extra=extra,
    )


def build_request_params(preferences: Mapping[str, Any]) -> dict[str, str]:
    """Build request query parameters from input preferences."""
    source_prefs = preferences.get("rapidapi") or preferences.get("jsearch")
    if not isinstance(source_prefs, Mapping):
        # Fallback to searchapi or global query
        q = preferences.get("q") or preferences.get("query")
        if isinstance(q, str) and q.strip():
            return {"query": q.strip(), "num_pages": "1"}
        return {}

    q = source_prefs.get("query") or source_prefs.get("q") or preferences.get("q")
    if not isinstance(q, str) or not q.strip():
        return {}

    params = {"query": q.strip()}

    if "num_pages" in source_prefs:
        params["num_pages"] = str(source_prefs["num_pages"])
    else:
        params["num_pages"] = "1"

    if "page" in source_prefs:
        params["page"] = str(source_prefs["page"])
    if "date_posted" in source_prefs:
        params["date_posted"] = str(source_prefs["date_posted"])
    if "remote_jobs_only" in source_prefs:
        params["remote_jobs_only"] = str(source_prefs["remote_jobs_only"]).lower()

    return params


class RapidApiAdapter:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: RapidApiClient,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._client = client
        self._max_pages = max_pages

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        """Search RapidAPI per input preferences."""
        params = build_request_params(preferences)
        warnings: list[SourceWarning] = []

        if not params:
            return FetchResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="no_query_requested",
                        message="no query or rapidapi search parameters present in preferences",
                    ),
                )
            )

        query = params["query"]
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        raw_count = 0
        errors: list[SourceError] = []

        try:
            payload = await self._client.search(params)
        except SourceError as exc:
            return FetchResult(
                jobs=(),
                warnings=(),
                errors=(exc,),
                raw_count=0,
            )

        try:
            response = RapidApiResponse.model_validate(payload)
        except ValidationError as exc:
            raise SourceValidationError(
                "response does not match RapidAPI schema",
                source=self.source_name,
                endpoint="search",
                cause=exc,
            ) from exc

        raw_count = len(response.data)

        for job_item in response.data:
            try:
                job = normalize_job(job_item, query=query)
            except Exception as exc:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="normalization_failed",
                        message=f"skipped item ({job_item.job_id}) during normalization: {exc}",
                    )
                )
                continue

            if job.source_job_id in seen_ids:
                continue
            seen_ids.add(job.source_job_id)
            jobs.append(job)

        logger.info(
            "rapidapi adapter run complete",
            extra={
                "source": self.source_name,
                "raw_count": raw_count,
                "jobs_normalized": len(jobs),
            },
        )
        return FetchResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            errors=tuple(errors),
            raw_count=raw_count,
        )
