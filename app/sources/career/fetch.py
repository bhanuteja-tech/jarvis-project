"""Guarded HTTP fetching for career pages.

Reuses the shared resilience engine (no second retry implementation).
Responsibilities:
- per-hop SSRF validation (scheme/port/host resolution) — redirects are
  followed MANUALLY so every destination re-passes the same gate;
- https->http downgrades are always rejected; http origins only when the
  configured allow-flag is set;
- redirect limit + visited-set loop detection;
- streamed hard byte cap (default 2 MiB) — oversized responses abort before
  consuming unbounded memory;
- content-type allowlist for page fetches (HTML/XHTML only);
- politeness: per-host lock + minimum inter-request delay.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.config.settings import Settings
from app.sources.career.errors import (
    ContentTooLargeError,
    RedirectLimitExceededError,
    RedirectLoopError,
    SourceSSRFBlockedError,
    UnsupportedContentTypeError,
)
from app.sources.career.models import FetchedPage
from app.sources.career.security import (
    USER_AGENT,
    Resolver,
    validate_and_resolve,
)
from app.sources.errors import SourceHTTPError
from app.sources.resilience import RETRYABLE_STATUS_CODES, RetryPolicy, execute_with_retry

logger = logging.getLogger(__name__)

PAGE_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/html", "application/xhtml+xml"}
)
ROBOTS_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/plain", "text/html", "application/octet-stream"}
)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class _HopResult:
    response: httpx.Response


def _normalize_content_type(value: str | None) -> str:
    return (value or "").split(";")[0].strip().lower()


class GuardedFetcher:
    source = "career_page"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep=None,
        jitter_rng=None,
        resolver: Resolver | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        from app.sources.resilience import full_jitter

        total = settings.career_fetch_timeout_seconds
        self._settings = settings
        self._resolver = resolver
        self._policy = RetryPolicy(max_attempts=settings.career_max_attempts)
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._jitter_rng = jitter_rng if jitter_rng is not None else full_jitter
        self._now = now if now is not None else time.monotonic
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=min(10.0, total), read=total, write=total, pool=min(5.0, total)
            ),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            transport=transport,
            follow_redirects=False,
        )
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}

    async def _politeness_wait(self, host: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            min_delay = self._settings.career_politeness_seconds
            elapsed_ok_at = self._host_last.get(host, 0.0) + min_delay
            wait_for = elapsed_ok_at - self._now()
            if wait_for > 0:
                await self._sleep(wait_for)
            self._host_last[host] = self._now()

    def _validate_hop(self, url: str) -> str:
        parts = urlsplit(url)
        host = parts.hostname or ""
        # Resolution happens in the async path; here we only need sync scheme/
        # port checks surfaced with precise errors before any I/O.
        from app.sources.career.security import validate_url

        validate_url(url, allow_http=self._settings.career_allow_http)
        return host

    async def _resolve_gate(self, url: str) -> None:
        await validate_and_resolve(self._settings, url, resolver=self._resolver)

    async def request_bytes(
        self,
        url: str,
        *,
        allowed_content_types: frozenset[str] | None = None,
        max_redirects: int | None = None,
    ) -> FetchedPage:
        """Fetch one URL through the full SSRF/redirect/cap gate."""
        max_hops = (
            max_redirects
            if max_redirects is not None
            else self._settings.career_max_redirects
        )
        current = url
        visited: dict[str, int] = {}
        hops: list[str] = []

        while True:
            self._validate_hop(current)
            await self._resolve_gate(current)
            host = urlsplit(current).hostname or ""
            await self._politeness_wait(host)

            response = await execute_with_retry(
                lambda target=current: self._single_request(target),
                policy=self._policy,
                context={"source": self.source, "operation": "fetch", "endpoint": current},
                sleep=self._sleep,
                jitter_rng=self._jitter_rng,
            )

            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                response.aclose()
                if not location:
                    raise SourceHTTPError(
                        "redirect response without Location header",
                        source=self.source,
                        endpoint=current,
                        status_code=response.status_code,
                        retryable=False,
                    )
                next_url = urljoin(current, location.strip())
                next_parts = urlsplit(next_url)
                if (
                    urlsplit(current).scheme.lower() == "https"
                    and next_parts.scheme.lower() == "http"
                    and not self._settings.career_allow_http
                ):
                    raise SourceSSRFBlockedError(
                        "https->http downgrade blocked",
                        reason="scheme_downgrade",
                        url=current,
                    )
                hops.append((next_parts.hostname or "").lower())
                if len(hops) > max_hops:
                    raise RedirectLimitExceededError(
                        f"exceeded {max_hops} redirects",
                        reason="redirect_limit_exceeded",
                        url=current,
                    )
                key = next_parts.netloc.lower() + next_parts.path
                if key in visited:
                    raise RedirectLoopError(
                        "redirect loop detected",
                        reason="redirect_loop",
                        url=next_url,
                    )
                visited[key] = len(visited)
                current = next_url
                continue

            content_type = _normalize_content_type(response.headers.get("content-type"))
            if allowed_content_types is not None and content_type not in allowed_content_types:
                response.aclose()
                logger.warning(
                    "career fetch rejected content type",
                    extra={
                        "source": self.source,
                        "operation": "fetch",
                        "url": current,
                        "content_type": content_type or "missing",
                    },
                )
                raise UnsupportedContentTypeError(
                    f"unsupported content type {content_type!r}",
                    reason="unsupported_content_type",
                    url=current,
                )

            body = await self._read_capped(response)

            return FetchedPage(
                requested_url=url,
                final_url=current,
                status_code=response.status_code,
                content_type=content_type,
                body=body,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )

    async def _read_capped(self, response: httpx.Response) -> bytes:
        cap = self._settings.career_max_bytes
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            await response.aclose()
            raise ContentTooLargeError(
                f"declared size {declared} exceeds cap {cap}",
                reason="content_too_large",
            )
        buffer = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                if len(buffer) > cap:
                    raise ContentTooLargeError(
                        f"streamed body exceeded cap {cap}",
                        reason="content_too_large",
                    )
        finally:
            await response.aclose()
        return bytes(buffer)

    async def _single_request(self, url: str) -> httpx.Response:
        response = await self._client.get(url)
        if response.status_code >= 400:
            retryable = response.status_code in RETRYABLE_STATUS_CODES
            await response.aclose()
            raise SourceHTTPError(
                f"unexpected HTTP status {response.status_code}",
                source=self.source,
                endpoint=url.split("?")[0],
                status_code=response.status_code,
                retryable=retryable,
            )
        return response

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = [
    "FetchedPage",
    "PAGE_CONTENT_TYPES",
    "ROBOTS_CONTENT_TYPES",
    "GuardedFetcher",
]
