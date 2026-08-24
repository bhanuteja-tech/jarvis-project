"""LLM provider retry/backoff engine.

Conservative retry logic for transient failures (timeouts, rate limits, server errors).
Never retries authentication failures, invalid model errors, or malformed responses.
Exponential backoff with full jitter; hard ceiling on max attempts.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from app.llm.base import (
    LLMProviderError,
    LLMTimeoutError,
    ProviderHTTPError,
    RateLimitedError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def full_jitter(delay: float) -> float:
    """AWS-style full jitter: uniform random sample over [0, delay]."""
    return random.uniform(0.0, delay)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # includes the first attempt
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 10.0
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


def _is_retryable_error(error: LLMProviderError) -> bool:
    """Determine if an error is retryable."""
    # Retry timeouts, rate limits, and server errors
    if isinstance(error, (LLMTimeoutError, RateLimitedError)):
        return True
    if isinstance(error, ProviderHTTPError):
        # ProviderHTTPError with 5xx status codes are retryable
        # This is heuristic; providers should set status_code on their errors
        return True
    # Never retry auth failures, invalid model, or malformed responses
    return False


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
        except LLMProviderError as exc:
            if not _is_retryable_error(exc) or attempt >= policy.max_attempts:
                logger.error(
                    "LLM provider call failed (non-retryable or max attempts reached)",
                    extra={
                        **ctx,
                        "attempt": attempt,
                        "max_attempts": policy.max_attempts,
                        "error_kind": type(exc).__name__,
                        "error_code": exc.code,
                    },
                )
                raise

            delay = jitter_rng(_backoff_delay(policy, attempt))
            logger.warning(
                "LLM provider call failed; scheduling retry (backoff=%0.3fs)",
                delay,
                extra={
                    **ctx,
                    "attempt": attempt,
                    "next_delay_seconds": round(delay, 3),
                    "error_kind": type(exc).__name__,
                    "error_code": exc.code,
                },
            )
            await sleep(delay)


__all__ = ["RetryPolicy", "execute_with_retry", "full_jitter"]
