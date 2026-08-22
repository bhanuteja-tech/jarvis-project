"""Canonical job domain model.

This is the single representation every source adapter must normalize into.
It is deliberately source-agnostic:

- Values absent from a source remain `None`; nothing is invented.
- Source timestamps (`source_*`) are kept strictly separate from internal
  timestamps (`discovered_at`, `fetched_at`).
- All datetimes are timezone-aware and normalized to UTC.
- `extra` carries optional provenance details without requiring schema
  redesign as new sources are added.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-naive datetimes are not allowed; use UTC-aware values")
    return value.astimezone(UTC)


class Salary(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    currency: str | None = None
    period: str | None = None


class Job(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str
    source_job_id: str
    title: str

    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    employment_type: str | None = None
    salary: Salary | None = None

    job_url: str | None = None
    apply_url: str | None = None

    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=utc_now)
    fetched_at: datetime = Field(default_factory=utc_now)

    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "source_job_id", "title")
    @classmethod
    def _reject_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator(
        "source_created_at",
        "source_updated_at",
        "discovered_at",
        "fetched_at",
    )
    @classmethod
    def _enforce_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None
