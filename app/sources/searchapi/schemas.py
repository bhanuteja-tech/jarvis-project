"""Pydantic models of the official SearchApi responses.

Contract verified against the official engine documentation on 2026-08-22:
- Google Jobs: https://www.searchapi.io/docs/google-jobs
- Google Search: https://www.searchapi.io/docs/google

The two engines do NOT share a result schema; they are modeled here as two
deliberately separate families and never mixed.

Key verified facts encoded:
- Both engines share one endpoint and auth (Bearer api key) only.
- google_jobs results carry NO job id, NO structured salary, and NO absolute
  timestamps. ``detected_extensions.posted_at`` is relative display text such
  as "1 day ago" and must NEVER be converted to a timestamp.
- google_search pagination uses a numeric ``page`` parameter; its response's
  ``pagination.next`` is a raw google.com URL which we never fetch.
- ``time_period`` freshness filtering is documented for google ONLY, never
  for google_jobs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SearchMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    status: str | None = None


class SearchParameters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    engine: str | None = None
    q: str | None = None
    hl: str | None = None
    gl: str | None = None


# ---------------------------------------------------------------------------
# Google Jobs family (engine=google_jobs)
# ---------------------------------------------------------------------------


class GoogleJobsHighlight(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    items: list[str] | None = None


class GoogleJobsApplyLink(BaseModel):
    model_config = ConfigDict(extra="ignore")

    link: HttpUrl | None = None
    source: str | None = None


class GoogleJobsJob(BaseModel):
    """One entry of the ``jobs`` array.

    Deliberately tolerant: optional-heavy because Google-derived payloads vary.
    """

    model_config = ConfigDict(extra="ignore")

    position: int | None = None
    title: str | None = None
    company_name: str | None = None
    location: str | None = None
    via: str | None = None
    description: str | None = None
    job_highlights: list[GoogleJobsHighlight] | None = None
    extensions: list[str] | None = None
    # Keys vary per posting (posted_at, schedule, health_insurance, ...).
    detected_extensions: dict[str, Any] | None = None
    apply_link: HttpUrl | None = None
    apply_links: list[GoogleJobsApplyLink] | None = None
    sharing_link: HttpUrl | None = None


class GoogleJobsPagination(BaseModel):
    model_config = ConfigDict(extra="ignore")

    next_page_token: str | None = None


class GoogleJobsResponse(BaseModel):
    """Top-level shape of an engine=google_jobs response.

    ``search_metadata`` is REQUIRED (present in every documented response);
    its absence means the payload is not a google_jobs response at all
    (e.g. a Data-API-shaped object) and fails validation.
    """

    model_config = ConfigDict(extra="ignore")

    search_metadata: SearchMetadata
    search_parameters: SearchParameters | None = None
    search_information: dict[str, Any] | None = None
    jobs: list[GoogleJobsJob] = Field(default_factory=list)
    pagination: GoogleJobsPagination | None = None


# ---------------------------------------------------------------------------
# Google Search family (engine=google)
# ---------------------------------------------------------------------------


class OrganicResult(BaseModel):
    """One entry of the ``organic_results`` array (discovery candidate)."""

    model_config = ConfigDict(extra="ignore")

    position: int | None = None
    title: str | None = None
    link: HttpUrl
    source: str | None = None
    domain: str | None = None
    displayed_link: str | None = None
    snippet: str | None = None
    #: Raw display text ("Nov 30, 2022", "21h ago"); ambiguous by design and
    #: never interpreted as a timestamp.
    date: str | None = None


class GoogleSearchResponse(BaseModel):
    """Top-level shape of an engine=google response (subset we consume).

    ``search_metadata`` is REQUIRED, mirroring google_jobs strictness.
    """

    model_config = ConfigDict(extra="ignore")

    search_metadata: SearchMetadata
    organic_results: list[OrganicResult] = Field(default_factory=list)
    #: {"current": int|None, "next": <google.com URL>}; the URL is never used.
    pagination: dict[str, Any] | None = None
