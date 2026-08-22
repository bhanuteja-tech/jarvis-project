"""Career-extractor typed error hierarchy.

All career failures extend the shared ``SourceError`` family with
``source="career_page"`` and a machine-readable ``reason`` so orchestration
can distinguish NO_JOB_DETECTED from FETCH_FAILED/EXTRACTION_FAILED without
string matching. Fetch transport failures reuse the shared
Timeout/Network/HTTP/Parse errors directly.
"""

from __future__ import annotations

from typing import Any

from app.sources.errors import SourceError

CAREER_SOURCE = "career_page"


class CareerPageError(SourceError):
    """Base class for career-page extraction failures."""

    def __init__(
        self,
        message: str,
        *,
        reason: str | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, source=CAREER_SOURCE, endpoint=url, **kwargs)
        self.reason = reason


class InvalidCareerUrlError(CareerPageError):
    """Input URL is malformed or unusable (reason=invalid_url)."""


class UnsupportedSchemeError(InvalidCareerUrlError):
    """URL scheme is not in the allowlist (reason=scheme_not_allowed)."""


class SourceSSRFBlockedError(CareerPageError):
    """Destination resolved to a blocked network/port (SSRF boundary).

    Reasons include: loopback, private_ip, link_local, cloud_metadata,
    multicast_or_reserved, unspecified_address, ipv4_mapped_private,
    port_not_allowed.
    """


class RedirectLimitExceededError(CareerPageError):
    """More redirects than the configured maximum."""


class RedirectLoopError(CareerPageError):
    """A redirect revisited an already-visited URL."""


class ContentTooLargeError(CareerPageError):
    """Response exceeded the streamed byte cap before completion."""


class UnsupportedContentTypeError(CareerPageError):
    """Response content type outside the HTML/XHTML allowlist."""


class RobotsDisallowedError(CareerPageError):
    """robots.txt explicitly disallows this path for our user agent."""


class RobotsUnavailableError(CareerPageError):
    """robots.txt could not be fetched/parsed under strict mode."""
