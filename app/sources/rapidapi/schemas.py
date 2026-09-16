"""Pydantic schemas for RapidAPI job search APIs (JSearch schema)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RapidApiJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: str = Field(..., description="Upstream job identifier")
    job_title: str | None = Field(default=None, description="Position title")
    employer_name: str | None = Field(default=None, description="Company/employer name")
    employer_logo: str | None = Field(default=None)
    employer_website: str | None = Field(default=None)
    job_publisher: str | None = Field(default=None)
    job_employment_type: str | None = Field(default=None)
    job_apply_link: str | None = Field(default=None)
    job_description: str | None = Field(default=None)
    job_is_remote: bool | None = Field(default=False)
    job_city: str | None = Field(default=None)
    job_state: str | None = Field(default=None)
    job_country: str | None = Field(default=None)
    job_posted_at_timestamp: int | float | None = Field(default=None)
    job_posted_at_datetime_utc: str | None = Field(default=None)
    job_min_salary: float | int | None = Field(default=None)
    job_max_salary: float | int | None = Field(default=None)
    job_salary_currency: str | None = Field(default=None)
    job_salary_period: str | None = Field(default=None)
    job_required_skills: list[str] | None = Field(default=None)
    job_required_experience: dict[str, Any] | None = Field(default=None)


class RapidApiResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = Field(default="OK")
    request_id: str | None = Field(default=None)
    data: list[RapidApiJob] = Field(default_factory=list)
