"""HTTP transport for RapidAPI job search endpoint (JSearch format).

Responsibilities (and nothing else):
- Send GET requests over httpx with explicit timeouts.
- Authenticate via `X-RapidAPI-Key` and `X-RapidAPI-Host` headers ONLY.
- Classify outcomes into the shared typed error hierarchy.
- Retry retryable failures via the shared resilience engine.
- Decode JSON into python objects.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
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

SOURCE_NAME = "rapidapi"
_USER_AGENT = "jarvis-job-discovery/0.1"


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class RapidApiClient:
    source = SOURCE_NAME

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        jitter_rng: Callable[[float], float] | None = None,
    ) -> None:
        key = (
            settings.rapidapi_api_key.get_secret_value().strip()
            or settings.x_rapidapi_key.get_secret_value().strip()
        )
        if not key:
            raise SourceConfigurationError(
                "RapidAPI is not configured: RAPIDAPI_API_KEY is empty",
                source=SOURCE_NAME,
            )
        self._api_key = key
        self._host = settings.rapidapi_host.strip()
        self._search_url = settings.rapidapi_search_url.rstrip("/")
        self._policy = RetryPolicy(max_attempts=settings.rapidapi_max_retries + 1)
        self._timeout = httpx.Timeout(
            connect=min(10.0, settings.rapidapi_timeout_seconds),
            read=settings.rapidapi_timeout_seconds,
            write=settings.rapidapi_timeout_seconds,
            pool=min(5.0, settings.rapidapi_timeout_seconds),
        )
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._jitter_rng = jitter_rng if jitter_rng is not None else full_jitter
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
                "X-RapidAPI-Key": self._api_key,
                "X-RapidAPI-Host": self._host,
            },
            transport=transport,
        )

    async def search(self, params: Mapping[str, Any]) -> Any:
        """Run one search request against the RapidAPI host."""
        payload = await execute_with_retry(
            lambda: self._get_json(self._search_url, dict(params)),
            policy=self._policy,
            context={"source": self.source, "operation": "search"},
            sleep=self._sleep,
            jitter_rng=self._jitter_rng,
        )
        logger.info(
            "rapidapi search completed",
            extra={
                "source": self.source,
                "operation": "search",
                "query": params.get("query"),
            },
        )
        return payload

    async def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        try:
            response = await self._client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(
                "request timed out",
                source=self.source,
                endpoint=url.split("?")[0],
                cause=exc,
            ) from exc
        except httpx.TransportError as exc:
            raise SourceNetworkError(
                f"network failure: {type(exc).__name__}",
                source=self.source,
                endpoint=url.split("?")[0],
                cause=exc,
            ) from exc

        if response.status_code == 429:
            raise SourceRateLimitError(
                "rate limited or quota exhausted upstream",
                source=self.source,
                endpoint=response.request.url.path,
                retry_after_seconds=_parse_retry_after(response.headers),
                cause=None,
            )
        if response.status_code >= 400:
            raise SourceHTTPError(
                f"unexpected HTTP status {response.status_code}",
                source=self.source,
                endpoint=response.request.url.path,
                status_code=response.status_code,
                retryable=response.status_code in RETRYABLE_STATUS_CODES,
            )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SourceParseError(
                "response body is not valid JSON",
                source=self.source,
                endpoint=response.request.url.path,
                cause=exc,
            ) from exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> RapidApiClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
