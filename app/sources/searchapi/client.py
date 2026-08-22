"""HTTP transport for the SearchApi search endpoint.

One client serves both engines (``google_jobs`` and ``google``): they share a
single endpoint and auth mechanism while their response schemas differ and are
modeled separately in ``schemas.py``.

Responsibilities (and nothing else):
- send one request per call over httpx with explicit timeouts,
- authenticate via the ``Authorization: Bearer`` header ONLY (the key never
  appears in URLs, query strings, logs, or exceptions),
- classify outcomes into the shared typed error hierarchy,
- retry retryable failures via the shared resilience engine (retries consume
  paid quota, so the default attempt count is deliberately small),
- decode JSON.

Engine-specific request building and all normalization live in the adapters.
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

SOURCE_NAME = "searchapi"

#: Engines this integration may call; anything else is rejected pre-flight.
ENGINES: frozenset[str] = frozenset({"google_jobs", "google"})

_USER_AGENT = "jarvis-job-discovery/0.1"


def validate_engine(engine: str) -> str:
    if engine not in ENGINES:
        raise SourceConfigurationError(
            f"unsupported SearchApi engine: {engine!r}",
            source=SOURCE_NAME,
        )
    return engine


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class SearchApiClient:
    source = SOURCE_NAME

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        jitter_rng: Callable[[float], float] | None = None,
    ) -> None:
        api_key = settings.searchapi_api_key.get_secret_value().strip()
        if not api_key:
            raise SourceConfigurationError(
                "SearchApi is not configured: SEARCHAPI_API_KEY is empty",
                source=SOURCE_NAME,
            )
        self._api_key = api_key
        self._search_url = settings.searchapi_search_url.rstrip("/")
        self._policy = RetryPolicy(max_attempts=settings.searchapi_max_retries + 1)
        self._timeout = self._build_timeout(settings.searchapi_timeout_seconds)
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._jitter_rng = jitter_rng if jitter_rng is not None else full_jitter
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
                "Authorization": f"Bearer {api_key}",
            },
            transport=transport,
        )

    @staticmethod
    def _build_timeout(total: float) -> httpx.Timeout:
        connect = min(10.0, total)
        pool = min(5.0, total)
        return httpx.Timeout(connect=connect, read=total, write=total, pool=pool)

    async def search(self, engine: str, params: Mapping[str, Any]) -> Any:
        """Run one search request for the given engine.

        `params` must be flat, URL-safe scalar values; adapters own their
        per-engine parameter whitelists. The key travels only in headers.
        """
        validated_engine = validate_engine(engine)
        merged = {"engine": validated_engine, **params}
        payload = await execute_with_retry(
            lambda: self._get_json(self._search_url, dict(merged)),
            policy=self._policy,
            context={"source": self.source, "operation": "search", "engine": validated_engine},
            sleep=self._sleep,
            jitter_rng=self._jitter_rng,
        )
        logger.info(
            "searchapi search completed",
            extra={
                "source": self.source,
                "operation": "search",
                "engine": validated_engine,
                "q": merged.get("q"),
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

    async def __aenter__(self) -> SearchApiClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
