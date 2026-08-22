"""Source-agnostic retry/backoff engine for outbound source calls.

The client raises typed `SourceError`s with a `retryable` flag already set;
this module owns the loop that decides whether to retry, how long to wait,
and when to give up. It knows nothing about any specific job source.

Behavior:
- Retries only errors whose `retryable` flag is True (429, 500, 502, 503,
  504, timeouts, transient network failures).
- Never retries non-retryable client errors or parse/validation failures.
- Exponential backoff with full jitter; honors `Retry-After` on HTTP 429
  when the upstream provides it (clamped to `max_backoff_seconds`).
- Hard ceiling: exactly `policy.max_attempts` attempts, never infinite.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from app.sources.errors import SourceError, SourceRateLimitError

logger = logging.getLogger(__name__)

#: Status codes considered reasonably retryable by every source adapter.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

T = TypeVar("T")


def full_jitter(delay: float) -> float:
    """AWS-style full jitter: uniform random sample over [0, delay]."""
    return random.uniform(0.0, delay)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4  # includes the first attempt
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must be >= 0")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")
        if self.backoff_multiplier <= 1:
            raise ValueError("backoff_multiplier must be > 1")


def _backoff_delay(policy: RetryPolicy, attempt: int) -> float:
    raw = policy.initial_backoff_seconds * (policy.backoff_multiplier ** (attempt - 1))
    return min(raw, policy.max_backoff_seconds)


async def execute_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    context: Mapping[str, Any] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter_rng: Callable[[float], float] = full_jitter,
) -> T:
    """Run `operation()` honoring `policy`.

    `sleep` and `jitter_rng` are injectable so tests can make timing fully
    deterministic and fast. `context` is attached to retry log records.
    """
    ctx = dict(context or {})
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except SourceError as exc:
            if not exc.retryable or attempt >= policy.max_attempts:
                exc.attempts = max(exc.attempts, attempt)
                raise
            if isinstance(exc, SourceRateLimitError) and exc.retry_after_seconds is not None:
                # Honor the server-provided window verbatim; jitter applies
                # only to our own exponential backoff.
                delay = min(max(exc.retry_after_seconds, 0.0), policy.max_backoff_seconds)
                reason = "retry_after"
            else:
                delay = jitter_rng(_backoff_delay(policy, attempt))
                reason = "backoff"
            logger.warning(
                "source call failed; scheduling retry (%s=%0.3fs)",
                reason,
                delay,
                extra={
                    **ctx,
                    "attempt": attempt,
                    "next_delay_seconds": round(delay, 3),
                    "error_kind": type(exc).__name__,
                    "status_code": exc.status_code,
                    "endpoint": exc.endpoint,
                    "source": exc.source,
                },
            )
            await sleep(delay)
