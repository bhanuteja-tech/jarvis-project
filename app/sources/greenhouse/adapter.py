"""GreenhouseAdapter: fetch -> validate -> normalize -> canonical Jobs.

The only module that maps Greenhouse-specific structures onto the canonical
`Job` model. It never invents values: fields the source does not provide
(company when absent from the registry, salary, employment type, structured
requirements) remain `None`.

Company identity follows approved Decision A: it comes from the configured
board registry (`board_token -> company_name`), never from the API response.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.models.job import Job
from app.sources.base import FetchResult, SourceWarning
from app.sources.errors import (
    SourceConfigurationError,
    SourceError,
    SourceValidationError,
)
from app.sources.greenhouse.client import (
    SOURCE_NAME,
    GreenhouseClient,
    validate_board_token,
)
from app.sources.greenhouse.registry import BoardRegistry, NullBoardRegistry
from app.sources.greenhouse.schemas import GreenhouseJobPost

logger = logging.getLogger(__name__)

_PREFERENCES_KEY = "greenhouse"
_BOARD_TOKENS_KEY = "board_tokens"


class _JobsSection(BaseModel):
    """Minimal structural contract of the top-level response."""

    model_config = ConfigDict(extra="ignore")

    jobs: list[object]


def _coerce_utc(value: datetime | None) -> datetime | None:
    """Aware datetimes become UTC; naive ones are dropped upstream of Job."""
    if value is None:
        return None
    if value.tzinfo is None:
        return None
    return value.astimezone(UTC)


def _blank_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def normalize_job_post(post: GreenhouseJobPost, *, company: str | None = None) -> Job:
    """Convert one validated Greenhouse post into a canonical `Job`."""
    job_url = str(post.absolute_url)

    return Job(
        source=SOURCE_NAME,
        source_job_id=str(post.id),
        title=post.title.strip(),
        company=_blank_to_none(company),
        location=_blank_to_none(post.location.name if post.location else None),
        description=post.content if post.content else None,
        requirements=None,
        responsibilities=None,
        employment_type=None,
        salary=None,
        job_url=job_url,
        apply_url=job_url,
        # first_published exists only on the single-job endpoint, which this
        # step deliberately does not call.
        source_created_at=None,
        source_updated_at=_coerce_utc(post.updated_at),
        extra={
            "internal_job_id": post.internal_job_id,
            "requisition_id": post.requisition_id,
            "language": post.language,
            "is_prospect": post.internal_job_id is None,
            # Opaque board-configured metadata, preserved as provenance only.
            "metadata": post.metadata,
        },
    )


class GreenhouseAdapter:
    source_name = SOURCE_NAME

    def __init__(self, client: GreenhouseClient, registry: BoardRegistry | None = None) -> None:
        self._client = client
        self._registry: BoardRegistry = registry if registry is not None else NullBoardRegistry()

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        """Fetch all boards named in ``preferences["greenhouse"]["board_tokens"]``."""
        source_prefs = preferences.get(_PREFERENCES_KEY)
        tokens: list[str] = []
        if isinstance(source_prefs, Mapping):
            requested = source_prefs.get(_BOARD_TOKENS_KEY)
            if isinstance(requested, (list, tuple)):
                tokens = [t for t in requested if isinstance(t, str)]

        if not tokens:
            return FetchResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="no_boards_requested",
                        message="no greenhouse board_tokens present in preferences",
                    ),
                )
            )

        seen: set[str] = set()
        ordered_unique = [t for t in tokens if not (t in seen or seen.add(t))]

        jobs: list[Job] = []
        warnings: list[SourceWarning] = []
        errors: list[SourceError] = []
        raw_count = 0

        for token in ordered_unique:
            try:
                result = await self.fetch_board(token)
            except SourceConfigurationError as exc:
                errors.append(exc)
                continue
            except SourceError as exc:
                logger.error(
                    "greenhouse board fetch failed",
                    extra={
                        "source": self.source_name,
                        "operation": "fetch_board",
                        "board_token": token,
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
            "greenhouse adapter run complete",
            extra={
                "source": self.source_name,
                "operation": "fetch_jobs",
                "boards_requested": len(ordered_unique),
                "boards_failed": len(errors),
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

    async def fetch_board(self, board_token: str) -> FetchResult:
        """Fetch, validate, and normalize all posts of a single board.

        Whole-request failures (transport, HTTP status, malformed JSON,
        structural mismatch) raise typed `SourceError`s. Per-item problems do
        not raise; they become warnings so partial data survives.
        """
        token = validate_board_token(board_token)
        endpoint = f"/{token}/jobs"

        raw = await self._client.list_jobs(token)

        try:
            section = _JobsSection.model_validate(raw)
        except ValidationError as exc:
            raise SourceValidationError(
                "response does not match the documented Greenhouse jobs schema",
                source=self.source_name,
                endpoint=endpoint,
                cause=exc,
            ) from exc

        company = self._registry.company_for(token)
        jobs: list[Job] = []
        warnings: list[SourceWarning] = []

        for index, item in enumerate(section.jobs):
            try:
                post = GreenhouseJobPost.model_validate(item)
            except ValidationError as exc:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="item_validation_failed",
                        message=(
                            f"job item at index {index} failed schema validation "
                            f"({exc.error_count()} error(s)); item skipped"
                        ),
                    )
                )
                continue

            try:
                jobs.append(normalize_job_post(post, company=company))
            except SourceError:
                raise
            except Exception as exc:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="normalization_failed",
                        message=(
                            f"skipped job post id={post.id} during normalization: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                )

            if post.updated_at is not None and post.updated_at.tzinfo is None:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="timestamp_dropped",
                        message=(
                            f"job post id={post.id} has timezone-naive updated_at; "
                            "source_updated_at set to null instead of assuming an offset"
                        ),
                    )
                )

        return FetchResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            raw_count=len(section.jobs),
        )
