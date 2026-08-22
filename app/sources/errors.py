"""Shared typed error hierarchy for external job sources.

Every adapter raises (or records) these errors so that failures remain
observable and distinguishable end-to-end. Instances carry provenance:
which source, which endpoint, how many attempts were made, whether the
failure is reasonably retryable, and the underlying cause when present.

No exception message ever contains credentials; endpoints are limited to
paths and non-sensitive query parameters constructed by our own clients.
"""

from __future__ import annotations

from typing import Any


class SourceError(Exception):
    """Base class for all job-source failures."""

    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        source: str,
        endpoint: str | None = None,
        attempts: int = 0,
        status_code: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.endpoint = endpoint
        self.attempts = attempts
        self.status_code = status_code
        self.cause = cause

    def __str__(self) -> str:
        parts = [f"[{self.source}] {self.message}"]
        if self.endpoint is not None:
            parts.append(f"endpoint={self.endpoint}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.attempts:
            parts.append(f"attempts={self.attempts}")
        if self.cause is not None:
            parts.append(f"cause={type(self.cause).__name__}: {self.cause}")
        return " | ".join(parts)

    def to_record(self) -> dict[str, Any]:
        """Serializable representation for orchestration state and logs."""
        return {
            "source": self.source,
            "kind": type(self).__name__,
            "retryable": self.retryable,
            "message": self.message,
            "endpoint": self.endpoint,
            "attempts": self.attempts,
            "status_code": self.status_code,
        }


class SourceTimeoutError(SourceError):
    """Connection or read timeout while contacting a source. Transient."""

    retryable = True


class SourceNetworkError(SourceError):
    """Non-timeout network failure (connection refused/reset, DNS). Transient."""

    retryable = True


class SourceHTTPError(SourceError):
    """Non-success HTTP response.

    `retryable` is decided at raise time from the documented retry policy
    (429/500/502/503/504 are retryable; other statuses are not).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, status_code=status_code, **kwargs)
        self.retryable = retryable


class SourceRateLimitError(SourceHTTPError):
    """HTTP 429 from a source. Retryable, optionally honoring Retry-After."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, status_code=429, retryable=True, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class SourceParseError(SourceError):
    """Response body could not be decoded as JSON."""


class SourceValidationError(SourceError):
    """Decoded response does not match the documented source schema."""


class SourceConfigurationError(SourceError):
    """Adapter inputs/configuration are invalid before any HTTP call is made."""
