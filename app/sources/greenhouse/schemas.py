"""Pydantic models of the official Greenhouse Job Board API responses.

Contract verified against the current official documentation at
https://docs.greenhouse.io/job-board.html on 2026-08-22.

Key documented facts encoded here:
- `GET /v1/boards/{board_token}/jobs` returns `{"jobs": [...], "meta": {...}}`.
  There is NO pagination parameter for this endpoint; the full set of job
  posts is returned in one response.
- Summary entries always carry: id, title, absolute_url; typically also
  updated_at (ISO-8601 with a UTC offset), location.name, language,
  internal_job_id (null for prospect posts), requisition_id, metadata.
- With `content=true`, each entry additionally carries `content` (HTML),
  `departments[]`, and `offices[]`.
- The list endpoint does NOT include company_name, first_published, salary,
  or employment type. Those are either single-job-endpoint fields or absent
  from this API entirely; we therefore never populate them from here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None


class GreenhouseDepartment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    parent_id: int | None = None


class GreenhouseOffice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    location: str | None = None
    parent_id: int | None = None


class GreenhouseJobPost(BaseModel):
    """One entry of the `jobs` array."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    internal_job_id: int | None = None  # null => prospect post
    title: str = Field(min_length=1)
    updated_at: datetime | None = None
    requisition_id: str | None = None
    location: GreenhouseLocation | None = None
    absolute_url: HttpUrl
    language: str | None = None
    metadata: object | None = None
    content: str | None = None  # HTML description; only present with content=true
    departments: list[GreenhouseDepartment] | None = None
    offices: list[GreenhouseOffice] | None = None


class GreenhouseJobsMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int | None = None


class GreenhouseJobsEnvelope(BaseModel):
    """Top-level shape of the jobs-list response."""

    model_config = ConfigDict(extra="ignore")

    jobs: list[GreenhouseJobPost]
    meta: GreenhouseJobsMeta | None = None
