"""Google Search discovery candidates (engine=google).

These are NOT canonical jobs and must never be treated as such: a search
snippet is not a verified job description. The eventual pipeline is::

    Google Search -> candidate URL -> Career Page Extractor -> canonical Job

The extractor is a later phase; this module only produces a clearly defined
candidate representation for it to consume later.

Pagination uses the documented numeric ``page`` parameter. Unlike the google
engine's response ``pagination.next`` (a raw google.com URL), we NEVER fetch
arbitrary URLs — pages advance by incrementing ``page`` until an empty result
page or the hard page ceiling.

Per the approved correction, ``time_period`` freshness filtering IS allowed
here (it is documented for this engine): last_1_minute ... last_30_minutes,
last_hour/day/week/month/year, plus custom time_period_min/max bounds.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.sources.base import SourceWarning
from app.sources.errors import SourceError, SourceValidationError
from app.sources.searchapi.client import SOURCE_NAME, SearchApiClient
from app.sources.searchapi.jobs_adapter import DEFAULT_MAX_PAGES, _blank_to_none
from app.sources.searchapi.schemas import GoogleSearchResponse

logger = logging.getLogger(__name__)

_PREFERENCES_KEY = "searchapi"
_SEARCH_KEY = "google_search"

#: Documented request parameters this adapter may emit for engine=google.
ALLOWED_SEARCH_PARAMS: frozenset[str] = frozenset(
    {
        "q",
        "location",
        "gl",
        "hl",
        "time_period",
        "time_period_min",
        "time_period_max",
    }
)

_VALID_TIME_PERIODS: frozenset[str] = frozenset(
    {
        "last_1_minute",
        "last_5_minutes",
        "last_15_minutes",
        "last_30_minutes",
        "last_hour",
        "last_day",
        "last_week",
        "last_month",
        "last_year",
    }
)


@dataclass(frozen=True)
class SearchCandidateResult:
    """A discovery candidate URL — input for a future page extractor."""

    position: int | None
    url: str
    title: str | None
    snippet: str | None
    site_source: str | None
    domain: str | None
    displayed_link: str | None
    #: Raw upstream display text; ambiguous by design, never a datetime.
    date_display: str | None
    query: str
    fetched_at: datetime


@dataclass(frozen=True)
class SearchCandidatesResult:
    candidates: tuple[SearchCandidateResult, ...] = ()
    warnings: tuple[SourceWarning, ...] = ()
    errors: tuple[SourceError, ...] = field(default=())
    raw_count: int = 0


def build_search_params(
    preferences: Mapping[str, Any],
) -> tuple[dict[str, str], list[str]]:
    """Build whitelisted engine=google request parameters.

    Returns ``(params, ignored_keys)``; ``params`` is empty when no usable
    ``q`` was supplied.
    """
    source_prefs = preferences.get(_PREFERENCES_KEY)
    search_prefs = (
        source_prefs.get(_SEARCH_KEY) if isinstance(source_prefs, Mapping) else None
    )
    if not isinstance(search_prefs, Mapping):
        return {}, []

    raw_q = search_prefs.get("q")
    if not isinstance(raw_q, str) or not raw_q.strip():
        return {}, []

    params = {"q": raw_q.strip()}
    ignored: list[str] = []
    for key, value in search_prefs.items():
        if not isinstance(key, str) or key == "q":
            continue
        if key in ALLOWED_SEARCH_PARAMS and isinstance(value, str) and value.strip():
            params[key] = value.strip()
        else:
            ignored.append(key)
    return params, sorted(set(ignored))


class GoogleSearchAdapter:
    source_name = SOURCE_NAME

    def __init__(
        self,
        client: SearchApiClient,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._client = client
        self._max_pages = max_pages

    async def search(self, preferences: Mapping[str, Any]) -> SearchCandidatesResult:
        """Discover candidate URLs per ``preferences["searchapi"]["google_search"]``."""
        params, ignored = build_search_params(preferences)
        warnings: list[SourceWarning] = []

        if not params:
            return SearchCandidatesResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="no_query_requested",
                        message="no searchapi.google_search.q present in preferences",
                    ),
                )
            )

        time_period = params.get("time_period")
        if time_period is not None and time_period not in _VALID_TIME_PERIODS:
            return SearchCandidatesResult(
                warnings=(
                    SourceWarning(
                        source=self.source_name,
                        code="invalid_time_period",
                        message=(
                            f"time_period={time_period!r} is not a documented "
                            f"value; valid values: {sorted(_VALID_TIME_PERIODS)}"
                        ),
                    ),
                )
            )

        if ignored:
            warnings.append(
                SourceWarning(
                    source=self.source_name,
                    code="unsupported_parameters_ignored",
                    message=(
                        "parameters not documented for engine=google were ignored: "
                        f"{', '.join(ignored)}"
                    ),
                )
            )

        query = params["q"]
        fetched_at = datetime.now(UTC)
        candidates: list[SearchCandidateResult] = []
        raw_count = 0
        page = 1

        while True:
            payload = await self._client.search("google", {**params, "page": page})

            try:
                response = GoogleSearchResponse.model_validate(payload)
            except ValidationError as exc:
                raise SourceValidationError(
                    "response does not match the documented google search schema",
                    source=self.source_name,
                    endpoint="google",
                    cause=exc,
                ) from exc

            results = response.organic_results
            if not results:
                break  # empty page => end of discovery

            raw_count += len(results)
            for result in results:
                candidates.append(
                    SearchCandidateResult(
                        position=result.position,
                        url=str(result.link),
                        title=_blank_to_none(result.title),
                        snippet=_blank_to_none(result.snippet),
                        site_source=_blank_to_none(result.source),
                        domain=_blank_to_none(result.domain),
                        displayed_link=_blank_to_none(result.displayed_link),
                        date_display=_blank_to_none(result.date),
                        query=query,
                        fetched_at=fetched_at,
                    )
                )

            if page >= self._max_pages:
                warnings.append(
                    SourceWarning(
                        source=self.source_name,
                        code="max_pages_reached",
                        message=(
                            f"stopped after {page} pages (hard ceiling); further "
                            "pages were not fetched"
                        ),
                    )
                )
                break
            page += 1

        logger.info(
            "google search discovery complete",
            extra={
                "source": self.source_name,
                "operation": "search",
                "pages_fetched": page,
                "raw_count": raw_count,
                "candidates_collected": len(candidates),
            },
        )
        return SearchCandidatesResult(
            candidates=tuple(candidates),
            warnings=tuple(warnings),
            raw_count=raw_count,
        )
