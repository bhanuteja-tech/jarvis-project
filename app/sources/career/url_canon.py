"""URL canonicalization for career pages.

Policy (approved):
- lowercase scheme/host; strip default ports; drop fragments;
- remove ONLY a fixed tracking-parameter set/prefix; every other query
  parameter is PRESERVED because career systems encode job identity there
  (gh_jid, jid, job, ashby_jid, ...);
- sort query parameters (order is semantically irrelevant per RFC 3986 and
  sorting gives deterministic identity);
- strip one trailing slash from non-root paths;
- NO percent-encoding renormalization beyond what urlsplit/urlunsplit round-
  trips preserve (aggressive requoting can damage meaningful encodings);
- NO www-stripping (host differentiation risk).
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "twclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "_hsenc",
        "_hsmi",
        "vero_id",
        "wickedid",
    }
)
TRACKING_PARAM_PREFIXES: tuple[str, ...] = ("utm_",)

DEFAULT_PORTS: dict[str, int] = {"https": 443, "http": 80}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    port = parts.port
    if port is not None and DEFAULT_PORTS.get(scheme) == port:
        netloc = host
    elif port is not None:
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_PARAM_NAMES
        and not key.lower().startswith(TRACKING_PARAM_PREFIXES)
    ]
    pairs.sort()
    query = urlencode(pairs)

    return urlunsplit((scheme, netloc, path, query, ""))


def canonicalize_with_declared(
    final_url: str,
    declared_canonical: str | None,
) -> tuple[str, bool]:
    """Apply canonicalization; honor <link rel=canonical> only when it points
    to the same HTTPS host. Returns (canonical_url, honored_flag)."""
    final_parts = urlsplit(final_url)
    if declared_canonical:
        declared_parts = urlsplit(declared_canonical.strip())
        same_host = (
            declared_parts.scheme.lower() == "https"
            and (declared_parts.hostname or "").lower()
            == (final_parts.hostname or "").lower()
        )
        if same_host:
            return canonicalize_url(declared_canonical), True
    return canonicalize_url(final_url), False


__all__ = [
    "canonicalize_url",
    "canonicalize_with_declared",
]
