"""HTTP transport for the Greenhouse Job Board API.

Responsibilities (and nothing else):
- build and send requests over httpx with explicit timeouts,
- classify outcomes into the shared typed error hierarchy,
- retry retryable failures via `app.sources.resilience`,
- decode JSON.

This module knows nothing about the canonical `Job` model, SQLAlchemy,
or LangGraph. Response *validation* against the documented schema happens
in `adapter.py`; only JSON decoding happens here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config.settings import Settings
from app.sources.errors import (
    SourceConfigurationError,
    SourceHTTPError,
    SourceNetworkError,
    SourceParseError,
    SourceRateLimitError,
    SourceTimeoutError,
)
from app.sources.resilience import (
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    execute_with_retry,
    full_jitter,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "greenhouse"

#: Board tokens are URL path slugs; anything else is rejected before a
#: request is ever built, preventing URL/path injection.
_BOARD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_USER_AGENT = "jarvis-job-discovery/0.1"


def validate_board_token(board_token: str) -> str:
    token = board_token.strip()
    if not _BOARD_TOKEN_PATTERN.fullmatch(token):
        raise SourceConfigurationError(
            "invalid Greenhouse board token",
            source=SOURCE_NAME,
        )
    return token


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    """Parse numeric `Retry-After` seconds; HTTP-dates are ignored."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class GreenhouseClient:
    source = SOURCE_NAME

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        jitter_rng: Callable[[float], float] | None = None,
    ) -> None:
        self._base_url = settings.greenhouse_base_url
        self._policy = RetryPolicy(max_attempts=settings.greenhouse_max_retries + 1)
        self._timeout = self._build_timeout(settings.greenhouse_timeout_seconds)
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._jitter_rng = jitter_rng if jitter_rng is not None else full_jitter
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            transport=transport,
        )

    @staticmethod
    def _build_timeout(total: float) -> httpx.Timeout:
        connect = min(10.0, total)
        pool = min(5.0, total)
        return httpx.Timeout(connect=connect, read=total, write=total, pool=pool)

    async def list_jobs(self, board_token: str) -> dict[str, Any]:
        """Fetch all published job posts for one board (`content=true`)."""
        token = validate_board_token(board_token)
        endpoint = f"/{token}/jobs"
        payload = await execute_with_retry(
            lambda: self._get_json(endpoint, params={"content": "true"}),
            policy=self._policy,
            context={"source": self.source, "operation": "list_jobs", "endpoint": endpoint},
            sleep=self._sleep,
            jitter_rng=self._jitter_rng,
        )
        logger.info(
            "greenhouse jobs fetched",
            extra={
                "source": self.source,
                "operation": "list_jobs",
                "endpoint": endpoint,
                "board_token": token,
                "job_count": len(payload.get("jobs") or []),
            },
        )
        return payload

    async def _get_json(self, endpoint: str, params: dict[str, str] | None) -> Any:
        try:
            response = await self._client.get(endpoint, params=params)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(
                "request timed out",
                source=self.source,
                endpoint=endpoint,
                cause=exc,
            ) from exc
        except httpx.TransportError as exc:
            raise SourceNetworkError(
                f"network failure: {type(exc).__name__}",
                source=self.source,
                endpoint=endpoint,
                cause=exc,
            ) from exc

        if response.status_code == 429:
            raise SourceRateLimitError(
                "rate limited by upstream",
                source=self.source,
                endpoint=endpoint,
                retry_after_seconds=_parse_retry_after(response.headers),
                cause=None,
            )
        if response.status_code >= 400:
            raise SourceHTTPError(
                f"unexpected HTTP status {response.status_code}",
                source=self.source,
                endpoint=endpoint,
                status_code=response.status_code,
                retryable=response.status_code in RETRYABLE_STATUS_CODES,
            )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SourceParseError(
                "response body is not valid JSON",
                source=self.source,
                endpoint=endpoint,
                cause=exc,
            ) from exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GreenhouseClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
