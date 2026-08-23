"""robots.txt gate (RFC 9309 semantics via stdlib robotparser).

Approved policy (correction #3):
- allowed  -> fetch proceeds;
- disallowed -> typed rejection, page never fetched;
- robots.txt unavailable/unreachable/unparseable -> REJECT in the default
  strict mode; `career_robots_permissive=True` allows proceeding with a
  warning. Neither mode constitutes a legal/ToS guarantee.

Per-host verdicts are cached for ``ttl_seconds`` (default 1h).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from app.config.settings import Settings
from app.sources.base import SourceWarning
from app.sources.career.errors import (
    RobotsDisallowedError,
    RobotsUnavailableError,
)
from app.sources.career.fetch import ROBOTS_CONTENT_TYPES, GuardedFetcher
from app.sources.errors import SourceHTTPError

logger = logging.getLogger(__name__)

_ROBOTS_MAX_BYTES = 262_144  # 256 KiB is far above any sane robots.txt


class RobotsGate:
    def __init__(
        self,
        fetcher: GuardedFetcher,
        settings: Settings,
        *,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._fetcher = fetcher
        self._settings = settings
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, bool]] = {}

    async def ensure_allowed(self, url: str) -> list[SourceWarning]:
        """Return warnings; raise RobotsDisallowedError / RobotsUnavailableError."""
        parts = urlsplit(url)
        host_root = f"{parts.scheme}://{parts.netloc}"
        cache_key = host_root.lower()

        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and cached[0] > now:
            self._raise_or_return(cached[1], url)
            return []

        verdict, warnings = await self._evaluate(host_root, url)
        self._cache[cache_key] = (now + self._ttl, verdict)
        self._raise_or_return(verdict, url)
        return warnings

    def _raise_or_return(self, verdict: bool, url: str) -> None:
        if not verdict:
            raise RobotsDisallowedError(
                "robots.txt disallows this path for our user agent",
                reason="robots_disallowed",
                url=url,
            )

    async def _evaluate(self, host_root: str, target_url: str) -> tuple[bool, list[SourceWarning]]:
        warnings: list[SourceWarning] = []
        robots_url = urljoin(host_root + "/", "robots.txt")

        try:
            page = await self._fetcher.request_bytes(
                robots_url,
                allowed_content_types=ROBOTS_CONTENT_TYPES,
                max_redirects=3,
            )
        except SourceHTTPError as exc:
            if exc.status_code == 404:
                # RFC 9309: a missing robots.txt imposes no restrictions.
                logger.info(
                    "robots.txt absent; no restrictions",
                    extra={"source": "career_page", "operation": "robots", "url": robots_url},
                )
                return True, warnings
            logger.warning(
                "robots.txt unreachable",
                extra={"source": "career_page", "operation": "robots", "host": host_root},
                exc_info=exc,
            )
            return self._handle_unavailable(warnings)
        except RobotsUnavailableError:
            raise
        except Exception as exc:  # transport failures of robots itself
            logger.warning(
                "robots.txt unreachable",
                extra={"source": "career_page", "operation": "robots", "host": host_root},
                exc_info=exc,
            )
            return self._handle_unavailable(warnings)

        parser = RobotFileParser()
        try:
            text = page.body.decode("utf-8", errors="replace")
            parser.parse(text.splitlines())
        except Exception as exc:  # pragma: no cover - parse() rarely raises
            logger.warning("robots.txt unparseable", extra={"url": robots_url})
            return self._handle_unavailable(warnings, cause=exc)

        # RFC 9309 group selection: the most specific matching user-agent
        # group governs. stdlib robotparser already unions every applicable
        # group, so querying with our product token alone is correct — the
        # wildcard fallback must NOT be able to override our own group's
        # Disallow rules.
        allowed = parser.can_fetch(_UA_TOKEN, target_url)
        if not allowed:
            logger.info(
                "robots.txt disallows path",
                extra={"source": "career_page", "operation": "robots", "url": target_url},
            )
        return allowed, warnings

    def _handle_unavailable(
        self, warnings: list[SourceWarning], *, cause: BaseException | None = None
    ) -> tuple[bool, list[SourceWarning]]:
        if self._settings.career_robots_permissive:
            warnings.append(
                SourceWarning(
                    source="career_page",
                    code="robots_unavailable_proceeded",
                    message=(
                        "robots.txt could not be retrieved; permissive mode allowed the fetch"
                    ),
                )
            )
            return True, warnings
        raise RobotsUnavailableError(
            "robots.txt unavailable and strict mode forbids proceeding",
            reason="robots_unavailable",
            cause=cause,
        )


_UA_TOKEN = "jarvis-job-discovery"

__all__ = ["RobotsGate"]
