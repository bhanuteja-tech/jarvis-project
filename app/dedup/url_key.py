"""URL comparison keys for cross-source identity (Tier A / rule R1).

Built on the frozen career canonicalizer: tracking parameters removed,
fragments dropped, trailing slashes normalized, query sorted, meaningful
parameters preserved. The comparison key additionally pins the scheme to
https and strips a leading ``www.`` — stored URLs are never modified.

SearchApi's Google ``sharing_link`` is deliberately excluded from Tier A
identity: it identifies Google's wrapper document, not the posting.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.sources.career.url_canon import canonicalize_url

_GOOGLE_HOSTS = frozenset({"google.com", "www.google.com"})
_LEADING_WWW_RE = re.compile(r"^www\.")


def _comparison_key(canonical_url: str) -> str:
    parts = urlsplit(canonical_url)
    host = _LEADING_WWW_RE.sub("", (parts.hostname or "").lower())
    path = parts.path or "/"
    key = f"https://{host}{path}"
    if parts.query:
        key = f"{key}?{parts.query}"
    return key


def job_url_key(job: Mapping[str, Any]) -> str | None:
    """Tier A comparison key from ``job_url``; None when unusable."""
    url = job.get("job_url")
    if not isinstance(url, str) or not url.strip():
        return None

    extra = job.get("extra") or {}
    engine = extra.get("engine")
    host = (urlsplit(url).hostname or "").lower()
    if engine == "google_jobs" and host in _GOOGLE_HOSTS:
        return None  # sharing_link excluded per plan §1

    return _comparison_key(canonicalize_url(url))


def apply_url_key(job: Mapping[str, Any]) -> str | None:
    """Corroboration-only key; never merges on its own (plan §4)."""
    url = job.get("apply_url")
    if not isinstance(url, str) or not url.strip():
        return None
    return _comparison_key(canonicalize_url(url))


__all__ = ["apply_url_key", "job_url_key"]
