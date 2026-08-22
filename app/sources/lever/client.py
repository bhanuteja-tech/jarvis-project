"""HTTP transport for the public Lever Postings API.

Responsibilities (and nothing else):
- build and send single-page requests over httpx with explicit timeouts,
- classify outcomes into the shared typed error hierarchy,
- retry retryable failures via ``app.sources.resilience``,
- decode JSON.

Pagination orchestration lives in the adapter; each call here fetches exactly
one page. This module knows nothing about the canonical ``Job`` model,
SQLAlchemy, or LangGraph. No authentication is sent: the public Postings API
requires none, and we never hold Lever credentials.
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

SOURCE_NAME = "lever"

#: Site names are URL path slugs; anything else is rejected before a request
#: is ever built, preventing URL/path injection.
_SITE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_USER_AGENT = "jarvis-job-discovery/0.1"


def validate_site(site: str) -> str:
    token = site.strip()
    if not _SITE_PATTERN.fullmatch(token):
        raise SourceConfigurationError(
            "invalid Lever site name",
            source=SOURCE_NAME,
        )
    return token


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    """Parse numeric ``Retry-After`` seconds; HTTP-dates are ignored."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class LeverClient:
    source = SOURCE_NAME

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        jitter_rng: Callable[[float], float] | None = None,
    ) -> None:
        self._base_url = settings.lever_base_url
        self._page_size = settings.lever_page_size
        self._policy = RetryPolicy(max_attempts=settings.lever_max_retries + 1)
        self._timeout = self._build_timeout(settings.lever_timeout_seconds)
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._jitter_rng = jitter_rng if jitter_rng is not None else full_jitter
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            transport=transport,
        )

    @property
    def page_size(self) -> int:
        return self._page_size

    @staticmethod
    def _build_timeout(total: float) -> httpx.Timeout:
        connect = min(10.0, total)
        pool = min(5.0, total)
        return httpx.Timeout(connect=connect, read=total, write=total, pool=pool)

    async def fetch_postings_page(
        self,
        site: str,
        *,
        skip: int = 0,
        limit: int | None = None,
    ) -> Any:
        """Fetch one page of postings for a site (bare array when valid)."""
        token = validate_site(site)
        effective_limit = limit if limit is not None else self._page_size
        endpoint = f"/{token}"
        payload = await execute_with_retry(
            lambda: self._get_json(
                endpoint,
                params={"mode": "json", "skip": skip, "limit": effective_limit},
            ),
            policy=self._policy,
            context={
                "source": self.source,
                "operation": "fetch_postings_page",
                "endpoint": endpoint,
            },
            sleep=self._sleep,
            jitter_rng=self._jitter_rng,
        )
        logger.info(
            "lever postings page fetched",
            extra={
                "source": self.source,
                "operation": "fetch_postings_page",
                "endpoint": endpoint,
                "site": token,
                "skip": skip,
                "limit": effective_limit,
                "item_count": len(payload) if isinstance(payload, list) else None,
            },
        )
        return payload

    async def _get_json(self, endpoint: str, params: dict[str, Any]) -> Any:
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

    async def __aenter__(self) -> LeverClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
