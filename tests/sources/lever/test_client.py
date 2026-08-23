"""HTTP-layer behavior of LeverClient (minimal regression over shared infra).

The shared retry/backoff engine is fully tested via the Greenhouse suite;
these tests prove only that the Lever client correctly routes through it.
Every test runs against httpx.MockTransport; no network access occurs.
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
from app.sources.lever.client import validate_site
from tests.support import (
    SITE,
    FakeSleeper,
    ScriptedRouter,
    connect_timeout,
    deterministic_jitter,
    json_response,
    load_lever_fixture,
    make_lever_client,
)


class TestSuccess:
    async def test_page_returns_bare_array(self) -> None:
        fixture = load_lever_fixture("postings_page.json")
        router = ScriptedRouter(json_response(fixture))
        client = make_lever_client(router)

        payload = await client.fetch_postings_page(SITE)

        assert isinstance(payload, list)
        assert len(payload) == 2

        request = router.last_request
        assert request is not None
        assert request.method == "GET"
        assert request.url.path.endswith(f"/{SITE}")
        assert request.url.params["mode"] == "json"
        assert request.url.params["skip"] == "0"
        assert request.url.params["limit"] == "50"
        assert "jarvis-job-discovery" in request.headers["User-Agent"]

    async def test_explicit_skip_and_limit_are_passed_through(self) -> None:
        router = ScriptedRouter(json_response([]))
        client = make_lever_client(router)

        await client.fetch_postings_page(SITE, skip=100, limit=5)

        request = router.last_request
        assert request is not None
        assert request.url.params["skip"] == "100"
        assert request.url.params["limit"] == "5"


class TestSiteValidation:
    @pytest.mark.parametrize("bad_site", ["", "  ", "../etc", "a b", "x/y", "üñí", "a" * 65])
    async def test_invalid_sites_rejected_without_http(self, bad_site: str) -> None:
        router = ScriptedRouter()
        client = make_lever_client(router)

        with pytest.raises(SourceConfigurationError):
            await client.fetch_postings_page(bad_site)

        assert router.call_count == 0

    @pytest.mark.parametrize("good_site", ["leverdemo", "ramp", "A-1_b"])
    def test_valid_sites_accepted(self, good_site: str) -> None:
        assert validate_site(good_site) == good_site


class TestSharedInfraRegression:
    """Prove reuse of the existing resilience engine — not a re-test of it."""

    async def test_unknown_site_404_fails_fast_without_retry(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(
            json_response(load_lever_fixture("error_404.json"), status_code=404)
        )
        client = make_lever_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.fetch_postings_page("no-such-site-zz9")

        assert excinfo.value.status_code == 404
        assert excinfo.value.retryable is False
        assert excinfo.value.attempts == 1
        assert router.call_count == 1
        assert fake_sleeper.delays == []

    async def test_429_uses_existing_retry_after_path_then_succeeds(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        fixture = load_lever_fixture("postings_page.json")
        router = ScriptedRouter(
            json_response({"ok": False}, status_code=429, headers={"Retry-After": "7"}),
            json_response(fixture),
        )
        client = make_lever_client(router, sleeper=fake_sleeper)

        payload = await client.fetch_postings_page(SITE)

        assert len(payload) == 2
        assert fake_sleeper.delays == [7.0]  # Retry-After honored verbatim
        assert router.call_count == 2

    async def test_persistent_503_raises_after_hard_ceiling(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(*[json_response({"ok": False}, status_code=503)] * 10)
        client = make_lever_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            lever_max_retries=1,
        )

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.fetch_postings_page(SITE)

        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 2  # initial + 1 retry
        assert router.call_count == 2

    async def test_timeout_maps_to_typed_retryable_error(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(*[connect_timeout] * 5)
        client = make_lever_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            lever_max_retries=1,
        )

        with pytest.raises(SourceTimeoutError) as excinfo:
            await client.fetch_postings_page(SITE)

        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 2

    async def test_malformed_json_is_not_retried(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(httpx.Response(200, content=b'{"postings": [{"id": "aaa'))
        client = make_lever_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceParseError):
            await client.fetch_postings_page(SITE)

        assert router.call_count == 1
        assert fake_sleeper.delays == []

    async def test_rate_limit_error_type_preserved_on_exhaustion(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(*[json_response({}, status_code=429)] * 10)
        client = make_lever_client(router, sleeper=fake_sleeper, lever_max_retries=1)

        with pytest.raises(SourceRateLimitError) as excinfo:
            await client.fetch_postings_page(SITE)

        assert excinfo.value.attempts == 2

    async def test_no_authorization_header_is_ever_sent(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_empty.json")))
        client = make_lever_client(router)

        await client.fetch_postings_page(SITE)

        request = router.last_request
        assert request is not None
        assert "authorization" not in {k.lower() for k in request.headers}
