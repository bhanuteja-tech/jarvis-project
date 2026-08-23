"""HTTP-layer behavior of GreenhouseClient: statuses, timeouts, retries.

Every test runs against httpx.MockTransport; no network access occurs.
"""

from __future__ import annotations

import httpx
import pytest

from app.sources.errors import (
    SourceConfigurationError,
    SourceHTTPError,
    SourceNetworkError,
    SourceParseError,
    SourceRateLimitError,
    SourceTimeoutError,
)
from app.sources.greenhouse.client import validate_board_token
from tests.support import (
    TOKEN,
    FakeSleeper,
    ScriptedRouter,
    connect_timeout,
    connection_refused,
    deterministic_jitter,
    json_response,
    load_fixture,
    load_fixture_text,
    make_client,
)


class TestSuccess:
    async def test_list_jobs_returns_envelope(self) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(json_response(fixture))
        client = make_client(router)

        payload = await client.list_jobs(TOKEN)

        assert len(payload["jobs"]) == 2
        assert payload["meta"]["total"] == 2

        request = router.last_request
        assert request is not None
        assert request.method == "GET"
        assert request.url.path.endswith(f"/{TOKEN}/jobs")
        assert request.url.params["content"] == "true"
        assert "jarvis-job-discovery" in request.headers["User-Agent"]

    async def test_empty_result_set_is_valid(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_empty.json")))
        client = make_client(router)

        payload = await client.list_jobs(TOKEN)

        assert payload["jobs"] == []


class TestBoardTokenValidation:
    @pytest.mark.parametrize("bad_token", ["", "  ", "../etc", "a b", "tok/en", "üñí", "a" * 65])
    async def test_invalid_tokens_rejected_without_http(self, bad_token: str) -> None:
        router = ScriptedRouter()
        client = make_client(router)

        with pytest.raises(SourceConfigurationError):
            await client.list_jobs(bad_token)

        assert router.call_count == 0

    @pytest.mark.parametrize("good_token", ["vaulttec", "very_awesome_inc", "A-1_b"])
    def test_valid_tokens_accepted(self, good_token: str) -> None:
        assert validate_board_token(good_token) == good_token


class TestNonRetryableStatuses:
    @pytest.mark.parametrize("status_code", [400, 401, 403, 404])
    async def test_client_errors_fail_fast(
        self, status_code: int, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(json_response({"message": "error"}, status_code=status_code))
        client = make_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.list_jobs(TOKEN)

        assert excinfo.value.status_code == status_code
        assert excinfo.value.retryable is False
        assert excinfo.value.attempts == 1
        assert excinfo.value.source == "greenhouse"
        assert excinfo.value.endpoint is not None and TOKEN in excinfo.value.endpoint
        assert router.call_count == 1
        assert fake_sleeper.delays == []

    async def test_malformed_json_is_not_retried(self, fake_sleeper: FakeSleeper) -> None:
        raw_body = load_fixture_text("malformed.json")
        router = ScriptedRouter(httpx.Response(200, content=raw_body.encode("utf-8")))
        client = make_client(router, sleeper=fake_sleeper)

        with pytest.raises(SourceParseError):
            await client.list_jobs(TOKEN)

        assert router.call_count == 1
        assert fake_sleeper.delays == []


class TestRetryableStatuses:
    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    async def test_server_errors_are_retried_until_success(
        self, status_code: int, fake_sleeper: FakeSleeper
    ) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(
            json_response({"message": "boom"}, status_code=status_code),
            json_response({"message": "boom"}, status_code=status_code),
            json_response(fixture),
        )
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
        )

        payload = await client.list_jobs(TOKEN)

        assert len(payload["jobs"]) == 2
        assert router.call_count == 3
        # base backoff 0.5s * 2^n with deterministic full-jitter factor 0.5.
        assert fake_sleeper.delays == [0.25, pytest.approx(0.5)]

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    async def test_server_errors_raise_after_max_attempts(
        self, status_code: int, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(*[json_response({"message": "down"}, status_code=status_code)] * 10)
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            greenhouse_max_retries=2,
        )

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.list_jobs(TOKEN)

        assert excinfo.value.status_code == status_code
        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 3  # initial + 2 retries (hard ceiling)
        assert router.call_count == 3


class TestRateLimiting:
    async def test_429_honors_retry_after_then_succeeds(self, fake_sleeper: FakeSleeper) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(
            json_response(
                {"message": "slow down"},
                status_code=429,
                headers={"Retry-After": "7"},
            ),
            json_response(fixture),
        )
        client = make_client(router, sleeper=fake_sleeper)

        payload = await client.list_jobs(TOKEN)

        assert len(payload["jobs"]) == 2
        # Retry-After honored verbatim (no jitter applied).
        assert fake_sleeper.delays == [7.0]
        assert router.call_count == 2

    async def test_429_without_header_uses_backoff(self, fake_sleeper: FakeSleeper) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(
            json_response({"message": "slow down"}, status_code=429),
            json_response(fixture),
        )
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
        )

        await client.list_jobs(TOKEN)

        assert fake_sleeper.delays == [0.25]

    async def test_persistent_429_raises_rate_limit_error(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(*[json_response({"message": "still slow"}, status_code=429)] * 10)
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            greenhouse_max_retries=1,
        )

        with pytest.raises(SourceRateLimitError) as excinfo:
            await client.list_jobs(TOKEN)

        assert excinfo.value.attempts == 2
        assert excinfo.value.retryable is True

    async def test_http_date_retry_after_falls_back_to_backoff(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(
            json_response(
                {"message": "slow down"},
                status_code=429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
            ),
            json_response(fixture),
        )
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
        )

        await client.list_jobs(TOKEN)

        assert fake_sleeper.delays == [0.25]


class TestTimeoutsAndNetworkErrors:
    async def test_timeout_is_retried_then_raises_typed_error(
        self, fake_sleeper: FakeSleeper
    ) -> None:
        router = ScriptedRouter(*[connect_timeout] * 5)
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            greenhouse_max_retries=1,
        )

        with pytest.raises(SourceTimeoutError) as excinfo:
            await client.list_jobs(TOKEN)

        assert excinfo.value.retryable is True
        assert excinfo.value.attempts == 2
        assert router.call_count == 2

    async def test_timeout_recovers_on_later_attempt(self, fake_sleeper: FakeSleeper) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(connect_timeout, json_response(fixture))
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
        )

        payload = await client.list_jobs(TOKEN)

        assert len(payload["jobs"]) == 2
        assert router.call_count == 2

    async def test_connection_error_maps_to_network_error(self, fake_sleeper: FakeSleeper) -> None:
        router = ScriptedRouter(*[connection_refused] * 5)
        client = make_client(
            router,
            sleeper=fake_sleeper,
            jitter=deterministic_jitter(0.5),
            greenhouse_max_retries=1,
        )

        with pytest.raises(SourceNetworkError) as excinfo:
            await client.list_jobs(TOKEN)

        assert excinfo.value.retryable is True
        assert router.call_count == 2


class TestSecretHygiene:
    async def test_error_output_contains_no_auth_headers_or_credentials(self) -> None:
        router = ScriptedRouter(json_response({"message": "nope"}, status_code=403))
        client = make_client(router)

        with pytest.raises(SourceHTTPError) as excinfo:
            await client.list_jobs(TOKEN)

        rendered = str(excinfo.value)
        assert "Authorization" not in rendered
        assert "secret" not in rendered.lower()

    async def test_request_never_carries_authorization_header(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))
        client = make_client(router)

        await client.list_jobs(TOKEN)

        request = router.last_request
        assert request is not None
        assert "authorization" not in {k.lower() for k in request.headers}
