"""GoogleSearchAdapter behavior: discovery candidates (NOT canonical jobs).

All HTTP is MockTransport; no network occurs.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.job import Job
from app.sources.base import FetchResult  # noqa: F401  (import guard below)
from app.sources.errors import SourceValidationError
from app.sources.searchapi.candidates import (
    GoogleSearchAdapter,
    SearchCandidateResult,
)
from tests.support import (
    ScriptedRouter,
    json_response,
    load_searchapi_fixture,
    make_searchapi_client,
)


def make_adapter(
    router: ScriptedRouter,
    *,
    max_pages: int | None = None,
    **client_overrides,
) -> GoogleSearchAdapter:
    client = make_searchapi_client(router, **client_overrides)
    kwargs = {"max_pages": max_pages} if max_pages is not None else {}
    return GoogleSearchAdapter(client, **kwargs)


def preferences(**extra_params) -> dict:
    params = {
        "q": "machine learning intern site:jobs.example.com",
        **extra_params,
    }
    return {"searchapi": {"google_search": params}}


async def collect(adapter: GoogleSearchAdapter):
    return await adapter.search(preferences())


def _two_page_router() -> ScriptedRouter:
    """Non-empty first page followed by the terminating empty page."""
    return ScriptedRouter(
        json_response(load_searchapi_fixture("google_search_page.json")),
        json_response(load_searchapi_fixture("google_search_empty.json")),
    )


class TestCandidateMapping:
    async def test_organic_results_map_onto_candidates(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        assert len(result.candidates) == 2
        assert result.raw_count == 2

        first = result.candidates[0]
        assert isinstance(first, SearchCandidateResult)
        assert first.url == "https://jobs.example.com/ml-intern-2026"
        assert first.title == "Machine Learning Intern — Example Corp Careers"
        assert first.snippet is not None and first.snippet.startswith("Example Corp")
        assert first.site_source == "Example Corp"
        assert first.domain == "jobs.example.com"
        assert first.displayed_link == "https://jobs.example.com › ml-intern-2026"
        # Raw display text preserved verbatim; never parsed as a datetime.
        assert first.date_display == "2 days ago"
        assert not isinstance(first.date_display, datetime)
        assert first.query == "machine learning intern site:jobs.example.com"

        second = result.candidates[1]
        assert second.snippet is None
        assert second.date_display is None

    async def test_run_shares_one_fetched_at_timestamp(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        fetched_ats = {candidate.fetched_at for candidate in result.candidates}
        assert len(fetched_ats) == 1
        assert next(iter(fetched_ats)).tzinfo is UTC

    async def test_candidates_are_not_canonical_jobs(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        for candidate in result.candidates:
            assert not isinstance(candidate, Job)


class TestPagination:
    async def test_empty_page_terminates_discovery(self) -> None:
        router = ScriptedRouter(
            json_response(load_searchapi_fixture("google_search_page.json")),
            json_response(load_searchapi_fixture("google_search_empty.json")),
        )
        adapter = make_adapter(router)

        result = await collect(adapter)

        assert len(result.candidates) == 2
        assert router.call_count == 2

    async def test_max_pages_guard_stops_longer_feeds(self) -> None:
        page = load_searchapi_fixture("google_search_page.json")  # non-empty page
        router = ScriptedRouter(*[json_response(page)] * 10)
        adapter = make_adapter(router, max_pages=1)

        result = await collect(adapter)

        assert router.call_count == 1
        codes = [w.code for w in result.warnings]
        assert "max_pages_reached" in codes


class TestApprovedCorrectionGuards:
    async def test_time_period_is_allowed_and_sent_for_google(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        await collect_with(adapter, time_period="last_30_minutes")

        request = router.last_request
        assert request is not None
        assert request.url.params["time_period"] == "last_30_minutes"

    async def test_invalid_time_period_rejected_without_http(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        result = await collect_with(adapter, time_period="last_fortnight")

        codes = [w.code for w in result.warnings]
        assert "invalid_time_period" in codes
        assert router.call_count == 0

    async def test_unsupported_parameters_dropped_with_warning(self) -> None:
        router = ScriptedRouter(
            json_response(load_searchapi_fixture("google_search_empty.json"))
        )
        adapter = make_adapter(router)

        result = await collect_with(adapter, num=100)

        message = next(
            w.message
            for w in result.warnings
            if w.code == "unsupported_parameters_ignored"
        )
        assert "num" in message


class TestPartialDataPolicy:
    async def test_no_query_requested_warns_and_makes_no_calls(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        result = await adapter.search({"searchapi": {"google_search": {"gl": "us"}}})

        assert result.candidates == ()
        assert result.warnings[0].code == "no_query_requested"
        assert router.call_count == 0

    async def test_structurally_wrong_payload_raises_validation_error(self) -> None:
        router = ScriptedRouter(
            json_response(load_searchapi_fixture("malformed_response.json"))
        )
        adapter = make_adapter(router)

        with pytest.raises(SourceValidationError):
            await collect(adapter)


async def collect_with(
    adapter: GoogleSearchAdapter,
    **extra_params,
):
    return await adapter.search(preferences(**extra_params))
