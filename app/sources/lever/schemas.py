"""Pydantic models of the official public Lever Postings API responses.

Contract verified against Lever's own documentation repository
(``github.com/lever/postings-api``) on 2026-08-22 and cross-checked with
read-only probes against the live public demo board.

Key facts encoded here:
- ``GET /v0/postings/{site}?mode=json`` returns a BARE JSON ARRAY of posting
  objects. There is no envelope; an object such as ``{"data": [...]}`` is the
  shape of the *authenticated Data API* (/v1), which we deliberately do not
  use, and is treated here as invalid.
- Pagination uses numeric ``skip``/``limit`` offsets. No total count exists.
- ``createdAt`` is epoch milliseconds observed in live responses but NOT part
  of the documented field list; it is therefore optional and defensive.
- No updated-at field exists anywhere in this API.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class LeverCategories(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location: str | None = None
    commitment: str | None = None
    team: str | None = None
    department: str | None = None
    allLocations: list[str] | None = None


class LeverListEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str | None = None
    content: str | None = None


class LeverSalaryRange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    currency: str | None = None
    interval: str | None = None
    min: float | None = None
    max: float | None = None


class LeverPosting(BaseModel):
    """One entry of the postings array."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    categories: LeverCategories | None = None
    country: str | None = None
    description: str | None = None
    descriptionPlain: str | None = None
    hostedUrl: HttpUrl
    applyUrl: HttpUrl
    workplaceType: str | None = None
    salaryRange: LeverSalaryRange | None = None
    salaryDescriptionPlain: str | None = None
    # Observed live but undocumented by Lever; parsed defensively only.
    createdAt: int | None = None
    lists: list[LeverListEntry] | None = None
