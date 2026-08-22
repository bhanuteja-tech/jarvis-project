"""Source-level persistence helpers.

`upsert_jobs` is persistence/upsert behavior ONLY. It is explicitly NOT
cross-source deduplication (Phase 1 Step 6) and performs no semantic
matching of any kind: identity is strictly `(source, source_job_id)`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobORM
from app.models.job import Job

logger = logging.getLogger(__name__)

#: Columns compared to decide whether a re-fetched job actually changed.
#: `id`, `discovered_at` and `fetched_at` are excluded by design.
_CONTENT_COLUMNS: tuple[str, ...] = (
    "title",
    "company",
    "location",
    "description",
    "requirements",
    "responsibilities",
    "employment_type",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "job_url",
    "apply_url",
    "source_created_at",
    "source_updated_at",
    "extra",
)


@dataclass(frozen=True)
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def _to_orm_fields(job: Job) -> dict[str, Any]:
    salary = job.salary
    return {
        "id": job.id,
        "source": job.source,
        "source_job_id": job.source_job_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "employment_type": job.employment_type,
        "salary_min": salary.min_amount if salary else None,
        "salary_max": salary.max_amount if salary else None,
        "salary_currency": salary.currency if salary else None,
        "salary_period": salary.period if salary else None,
        "job_url": job.job_url,
        "apply_url": job.apply_url,
        "source_created_at": job.source_created_at,
        "source_updated_at": job.source_updated_at,
        "discovered_at": job.discovered_at,
        "fetched_at": job.fetched_at,
        "extra": job.extra or None,
    }


def _row_signature(row: JobORM) -> tuple[Any, ...]:
    return tuple(getattr(row, column) for column in _CONTENT_COLUMNS)


def _values_signature(values: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(values[column] for column in _CONTENT_COLUMNS)


def upsert_jobs(session: Session, jobs: Iterable[Job]) -> UpsertStats:
    """Persist canonical jobs keyed by `(source, source_job_id)`.

    - new jobs are inserted with their own `discovered_at`;
    - changed jobs get their content columns and `fetched_at` updated while
      the original `discovered_at` is preserved;
    - identical jobs leave the row untouched;
    - the session is committed on success.
    """
    stats_inserted = 0
    stats_updated = 0
    stats_unchanged = 0
    for job in jobs:
        fields = _to_orm_fields(job)
        existing = session.execute(
            select(JobORM).where(
                JobORM.source == job.source,
                JobORM.source_job_id == job.source_job_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(JobORM(**fields))
            stats_inserted += 1
            continue

        content_changed = _row_signature(existing) != _values_signature(fields)
        if not content_changed:
            stats_unchanged += 1
            continue

        for column in _CONTENT_COLUMNS:
            setattr(existing, column, fields[column])
        existing.fetched_at = fields["fetched_at"]
        stats_updated += 1

    session.commit()
    stats = UpsertStats(
        inserted=stats_inserted,
        updated=stats_updated,
        unchanged=stats_unchanged,
    )
    logger.info(
        "jobs persisted",
        extra={
            "operation": "upsert_jobs",
            "inserted": stats.inserted,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
        },
    )
    return stats


__all__ = ["UpsertStats", "upsert_jobs"]
