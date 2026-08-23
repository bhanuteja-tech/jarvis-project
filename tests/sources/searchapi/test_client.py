"""HTTP-layer behavior of SearchApiClient (minimal shared-infra regression).

The shared retry/backoff engine is fully tested via the Greenhouse suite;
these tests prove only that the SearchApi client routes through it correctly
and never leaks the API key. All HTTP is MockTransport; no network occurs.
"""

from __future__ import annotations

import httpx
import pytest

from app.sources.errors import (
    SourceConfigurationError,
    SourceHTTPError,
    SourceParseError,
    SourceRateLimitError,
    SourceTimeoutError,
)
from app.sources.searchapi.client import validate_engine
from tests.support import (
    FakeSleeper,
    ScriptedRouter,
    connect_timeout,
    deterministic_jitter,
    json_response,
    load_searchapi_fixture,
    make_searchapi_client,
)

ENGINE = "google_jobs"
QUERY = "machine learning intern"


class TestConfiguration:
    @pytest.mark.parametrize("missing_key", ["", "   "])
    def test_missing_api_key_rejected_at_construction(self, missing_key: str) -> None:
        with pytest.raises(SourceConfigurationError):
            make_searchapi_client(ScriptedRouter(), searchapi_api_key=missing_key)

    async def test_unsupported_engine_rejected_without_http(self) -> None:
        router = ScriptedRouter()
        client = make_searchapi_client(router)

        with pytest.raises(SourceConfigurationError):
            await client.search("bing", {"q": QUERY})

        assert router.call_count == 0

    def test_validate_engine_accepts_documented_engines(self) -> None:
        assert validate_engine("google_jobs") == "google_jobs"
        assert validate_engine("google") == "google"


class TestSuccess:
    async def test_search_returns_parsed_payload(self) -> None:
        fixture = load_searchapi_fixture("jobs_page.json")
        router = ScriptedRouter(json_response(fixture))
        client = make_searchapi_client(router)

        payload = await client.search(ENGINE, {"q": QUERY})

        assert payload["search_metadata"]["status"] == "Success"

        request = router.last_request
        assert request is not None
        assert request.method == "GET"
        assert request.url.path == "/api/v1/search"
        assert request.url.params["engine"] == ENGINE
        assert request.url.params["q"] == QUERY
        assert request.headers["Authorization"] == "Bearer test-key"
        assert "jarvis-job-discovery" in request.headers["User-Agent"]

    async def test_api_key_never_appears_in_the_url(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_empty.json")))
        client = make_searchapi_client(router)

        await client.search(ENGINE, {"q": QUERY, "next_page_token": "abc"})

        request = router.last_request
        assert request is not None
        assert "test-key" not in str(request.url)


class TestSharedInfraRegression:
    """Prove reuse of the existing engine — not a re-test of its internals."""

    async def test_401_invalid_key_fails_fast_without_retry(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(
            json_response(load_searchapi_fixture("error_401.json"), status_code=401)
        )
        client = make_searchapi_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.search(ENGINE, {"q": QUERY})

        assert excinfo.value.status_code == 401
        assert excinfo.value.retryable is False
        assert excinfo.value.attempts == 1
        assert router.call_count == 1
        assert fake_sleeper.delays == []

    async def test_429_uses_existing_retry_after_path_then_succeeds(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        fixture = load_searchapi_fixture("jobs_page.json")
        router = ScriptedRouter(
            json_response({"error": "quota"}, status_code=429, headers={"Retry-After": "7"}),
            json_response(fixture),
        )
        client = make_searchapi_client(router, sleeper=fake_sleeper)

        payload = await client.search(ENGINE, {"q": QUERY})

        assert payload["search_metadata"]["status"] == "Success"
        assert fake_sleeper.delays == [7.0]
        assert router.call_count == 2

    async def test_persistent_503_raises_after_hard_ceiling(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(*[json_response({}, status_code=503)] * 10)
        client = make_searchapi_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            searchapi_max_retries=1,
        )

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.search(ENGINE, {"q": QUERY})

        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 2  # initial + 1 retry
        assert router.call_count == 2

    async def test_persistent_429_raises_rate_limit_error(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(*[json_response({}, status_code=429)] * 10)
        client = make_searchapi_client(router, sleeper=fake_sleeper, searchapi_max_retries=1)

        with pytest.raises(SourceRateLimitError) as excinfo:
            await client.search(ENGINE, {"q": QUERY})

        assert excinfo.value.attempts == 2

    async def test_timeout_maps_to_typed_retryable_error(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(*[connect_timeout] * 5)
        client = make_searchapi_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            searchapi_max_retries=1,
        )

        with pytest.raises(SourceTimeoutError) as excinfo:
            await client.search(ENGINE, {"q": QUERY})

        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 2

    async def test_malformed_json_is_not_retried(self, fake_sleeper: FakeSleeper) -> None:
        raw_body = '{"search_metadata": {"status": "Trunc'
        router = ScriptedRouter(httpx.Response(200, content=raw_body.encode("utf-8")))
        client = make_searchapi_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceParseError):
            await client.search(ENGINE, {"q": QUERY})

        assert router.call_count == 1
        assert fake_sleeper.delays == []
