"""Explicitly opt-in live smoke tests against the real SearchApi API.

Excluded from normal runs twice over:
1. The ``live`` marker is deselected by default (see pyproject ``addopts``).
2. Even with ``-m live``, it requires ``JARVIS_RUN_LIVE_SMOKE=1``.

Additionally, each test SKIPS when ``SEARCHAPI_API_KEY`` is not configured.

IMPORTANT: every executed test consumes exactly ONE billable SearchApi
request from the account quota (e.g. the 100 free requests). They are never
run by CI and never run automatically.

Run explicitly with::

    JARVIS_RUN_LIVE_SMOKE=1 pytest -m live tests/test_searchapi_live_smoke.py
"""

from __future__ import annotations

import os

import pytest

from app.config.settings import get_settings
from app.sources.searchapi.candidates import GoogleSearchAdapter
from app.sources.searchapi.client import SearchApiClient
from app.sources.searchapi.jobs_adapter import GoogleJobsAdapter

pytestmark = [pytest.mark.live]


def _smoke_enabled() -> bool:
    return os.environ.get("JARVIS_RUN_LIVE_SMOKE") == "1"


def _client() -> SearchApiClient:
    return SearchApiClient(get_settings())


async def test_live_searchapi_google_jobs_smoke() -> None:
    if not _smoke_enabled():
        pytest.skip(
            "live smoke disabled by default; run explicitly with "
            "JARVIS_RUN_LIVE_SMOKE=1 pytest -m live"
        )
    if not get_settings().searchapi_api_key.get_secret_value():
        pytest.skip("SEARCHAPI_API_KEY not configured; refusing to run live smoke")

    adapter = GoogleJobsAdapter(_client(), max_pages=1)
    result = await adapter.fetch_jobs(
        {"searchapi": {"google_jobs": {"q": "machine learning intern"}}}
    )

    assert not result.errors
    print(
        f"\nlive smoke OK: engine=google_jobs consumed 1 request; "
        f"raw={result.raw_count} jobs={len(result.jobs)}"
    )


async def test_live_searchapi_google_search_smoke() -> None:
    if not _smoke_enabled():
        pytest.skip(
            "live smoke disabled by default; run explicitly with "
            "JARVIS_RUN_LIVE_SMOKE=1 pytest -m live"
        )
    if not get_settings().searchapi_api_key.get_secret_value():
        pytest.skip("SEARCHAPI_API_KEY not configured; refusing to run live smoke")

    adapter = GoogleSearchAdapter(_client(), max_pages=1)
    query = '"machine learning intern" (site:jobs.lever.co OR site:boards.greenhouse.io)'
    result = await adapter.search({"searchapi": {"google_search": {"q": query}}})

    assert not result.errors
    print(f"\nlive smoke OK: engine=google consumed 1 request; candidates={len(result.candidates)}")
