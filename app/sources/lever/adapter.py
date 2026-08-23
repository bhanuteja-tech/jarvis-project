"""LeverAdapter: paginated fetch -> validate -> normalize -> canonical Jobs.

The only module that maps public Lever Postings API structures onto the
canonical ``Job`` model. It never invents values:

- company comes from the configured site registry (Decision A), or stays None;
- ``source_updated_at`` stays None because this API has no updated-at field;
- ``requirements``/``responsibilities`` stay None — Lever's free-form
  ``lists`` are preserved verbatim in ``extra``; semantic extraction belongs
  to Phase 2.

Pagination follows the verified offset contract: request ``limit`` per page,
stop at an empty or short page, suppress duplicate ids across pages (offset
feeds can shift mid-run), and stop hard at ``max_pages``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.models.job import Job, Salary
from app.sources.base import FetchResult, SourceWarning
from app.sources.errors import (
    SourceConfigurationError,
    SourceError,
    SourceValidationError,
)
from app.sources.lever.client import SOURCE_NAME, LeverClient, validate_site
from app.sources.lever.registry import NullSiteRegistry, SiteRegistry
from app.sources.lever.schemas import LeverPosting

logger = logging.getLogger(__name__)

_PREFERENCES_KEY = "lever"
_SITES_KEY = "sites"

DEFAULT_MAX_PAGES = 200


def _blank_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def epoch_ms_to_utc(value: int) -> datetime | None:
    """Convert epoch-milliseconds to UTC; out-of-range inputs yield None."""
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def normalize_posting(
    posting: LeverPosting,
    *,
    company: str | None = None,
    source_created_at: datetime | None = None,
) -> Job:
    """Convert one validated Lever posting into a canonical ``Job``."""
    job_url = str(posting.hostedUrl)
    apply_url = str(posting.applyUrl)
    categories = posting.categories

    salary: Salary | None = None
    if posting.salaryRange is not None:
        salary_range = posting.salaryRange
        if any(
            value is not None
            for value in (
                salary_range.min,
                salary_range.max,
                salary_range.currency,
                salary_range.interval,
            )
        ):
            salary = Salary(
                min_amount=(
                    Decimal(str(salary_range.min)) if salary_range.min is not None else None
                ),
                max_amount=(
                    Decimal(str(salary_range.max)) if salary_range.max is not None else None
                ),
                currency=_blank_to_none(salary_range.currency),
                period=_blank_to_none(salary_range.interval),
            )

    extra = {
        "description_plain": _blank_to_none(posting.descriptionPlain),
        "team": _blank_to_none(categories.team) if categories else None,
        "department": _blank_to_none(categories.department) if categories else None,
        "workplace_type": _blank_to_none(posting.workplaceType),
        "country": _blank_to_none(posting.country),
        "all_locations": categories.allLocations if categories else None,
        # Verbatim provenance for Phase 2 JD intelligence; deliberately never
        # promoted into requirements/responsibilities by name heuristics.
        "lists": (
            [{"text": entry.text, "content": entry.content} for entry in posting.lists]
            if posting.lists
            else None
        ),
        "salary_description_plain": _blank_to_none(posting.salaryDescriptionPlain),
    }

    return Job(
        source=SOURCE_NAME,
        source_job_id=posting.id.strip(),
        title=posting.text.strip(),
        company=_blank_to_none(company),
        location=_blank_to_none(categories.location) if categories else None,
        description=posting.description if posting.description else None,
        requirements=None,
        responsibilities=None,
        employment_type=_blank_to_none(categories.commitment) if categories else None,
        salary=salary,
        job_url=job_url,
        apply_url=apply_url,
        source_created_at=source_created_at,
        # The public Postings API exposes no updated-at field; never invented.
        source_updated_at=None,
        extra=extra,
    )


class LeverAdapter:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: LeverClient,
        registry: SiteRegistry | None = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._client = client
        self._registry: SiteRegistry = registry if registry is not None else NullSiteRegistry()
        self._page_size = client.page_size
        self._max_pages = max_pages

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        """Fetch all sites named in ``preferences["lever"]["sites"]``."""
        source_prefs = preferences.get(_PREFERENCES_KEY)
        sites: list[str] = []
        if isinstance(source_prefs, Mapping):
            requested = source_prefs.get(_SITES_KEY)
            if isinstance(requested, (list, tuple)):
                sites = [s for s in requested if isinstance(s, str)]

        if not sites:
            return FetchResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="no_sites_requested",
                        message="no lever sites present in preferences",
                    ),
                )
            )

        seen: set[str] = set()
        ordered_unique = [s for s in sites if not (s in seen or seen.add(s))]

        jobs: list[Job] = []
        warnings: list[SourceWarning] = []
        errors: list[SourceError] = []
        raw_count = 0

        for site in ordered_unique:
            try:
                result = await self.fetch_site(site)
            except SourceConfigurationError as exc:
                errors.append(exc)
                continue
            except SourceError as exc:
                logger.error(
                    "lever site fetch failed",
                    extra={
                        "source": self.source_name,
                        "operation": "fetch_site",
                        "site": site,
                        "error_kind": type(exc).__name__,
                        "status_code": exc.status_code,
                        "endpoint": exc.endpoint,
                        "attempts": exc.attempts,
                    },
                )
                errors.append(exc)
                continue
            jobs.extend(result.jobs)
            warnings.extend(result.warnings)
            errors.extend(result.errors)
            raw_count += result.raw_count

        skipped = sum(1 for w in warnings if w.code == "item_validation_failed")
        logger.info(
            "lever adapter run complete",
            extra={
                "source": self.source_name,
                "operation": "fetch_jobs",
                "sites_requested": len(ordered_unique),
                "sites_failed": len(errors),
                "raw_count": raw_count,
                "jobs_normalized": len(jobs),
                "items_skipped": skipped,
            },
        )
        return FetchResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            errors=tuple(errors),
            raw_count=raw_count,
        )

    async def fetch_site(self, site: str) -> FetchResult:
        """Fetch, validate, and normalize all postings of a single site.

        Whole-request failures (transport, HTTP status, malformed JSON,
        structural mismatch) raise typed ``SourceError``s; per-site callers
        capture them. Per-item problems do not raise; they become warnings so
        partial data survives.
        """
        token = validate_site(site)
        endpoint = f"/{token}"
        company = self._registry.company_for(token)

        jobs: list[Job] = []
        warnings: list[SourceWarning] = []
        seen_ids: set[str] = set()
        raw_count = 0
        pages = 0
        skip = 0

        while True:
            page = await self._client.fetch_postings_page(token, skip=skip)

            if not isinstance(page, list):
                raise SourceValidationError(
                    "postings response is not a JSON array",
                    source=self.source_name,
                    endpoint=endpoint,
                )

            pages += 1
            raw_count += len(page)

            for index, item in enumerate(page):
                try:
                    posting = LeverPosting.model_validate(item)
                except ValidationError as exc:
                    warnings.append(
                        SourceWarning(
                            source=self.source_name,
                            code="item_validation_failed",
                            message=(
                                f"posting item at index {index} failed schema "
                                f"validation ({exc.error_count()} error(s)); item skipped"
                            ),
                        )
                    )
                    continue

                if posting.id in seen_ids:
                    warnings.append(
                        SourceWarning(
                            source=self.source_name,
                            code="duplicate_skipped",
                            message=(
                                f"posting id={posting.id} was already collected on an "
                                "earlier page; duplicate skipped"
                            ),
                        )
                    )
                    continue
                seen_ids.add(posting.id)

                created_at: datetime | None = None
                if posting.createdAt is not None:
                    created_at = epoch_ms_to_utc(posting.createdAt)
                    if created_at is None:
                        warnings.append(
                            SourceWarning(
                                source=self.source_name,
                                code="timestamp_dropped",
                                message=(
                                    f"posting id={posting.id} has out-of-range "
                                    f"createdAt={posting.createdAt}; "
                                    "source_created_at set to null"
                                ),
                            )
                        )

                try:
                    jobs.append(
                        normalize_posting(posting, company=company, source_created_at=created_at)
                    )
                except SourceError:
                    raise
                except Exception as exc:
                    warnings.append(
                        SourceWarning(
                            source=self.source_name,
                            code="normalization_failed",
                            message=(
                                f"skipped posting id={posting.id} during normalization: "
                                f"{type(exc).__name__}: {exc}"
                            ),
                        )
                    )

            if len(page) < self._page_size:
                break  # short page (or empty page) => end of results

            if pages >= self._max_pages:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="max_pages_reached",
                        message=(
                            f"stopped after {pages} pages (hard ceiling); any further "
                            "pages were not fetched"
                        ),
                    )
                )
                break

            skip += len(page)

        return FetchResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            raw_count=raw_count,
        )
