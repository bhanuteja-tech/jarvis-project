"""Career Page Extractor package.

Consumes candidate URLs (e.g. from SearchApi discovery) and produces VERIFIED
canonical jobs — or explicit structured non-success. A search snippet is
never treated as job data; only content actually fetched from the page counts.

Public surface: :class:`CareerPageExtractor` returning
:class:`~app.sources.career.models.ExtractionResult`.
"""

from __future__ import annotations

from app.sources.career.errors import (
    CareerPageError,
    ContentTooLargeError,
    InvalidCareerUrlError,
    RedirectLimitExceededError,
    RedirectLoopError,
    RobotsDisallowedError,
    RobotsUnavailableError,
    SourceSSRFBlockedError,
    UnsupportedContentTypeError,
    UnsupportedSchemeError,
)
from app.sources.career.extract import CareerPageExtractor
from app.sources.career.models import ExtractionResult, ExtractionStatus

__all__ = [
    "CareerPageError",
    "CareerPageExtractor",
    "ContentTooLargeError",
    "ExtractionResult",
    "ExtractionStatus",
    "InvalidCareerUrlError",
    "RedirectLimitExceededError",
    "RedirectLoopError",
    "RobotsDisallowedError",
    "RobotsUnavailableError",
    "SourceSSRFBlockedError",
    "UnsupportedContentTypeError",
    "UnsupportedSchemeError",
]
