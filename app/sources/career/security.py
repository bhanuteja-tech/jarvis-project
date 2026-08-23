"""SSRF boundary: scheme/port/host validation for untrusted candidate URLs.

Every URL — initial or redirect destination — passes through
:func:`validate_url` and its host through :func:`assert_public_host`.
Blocked networks: loopback, private (RFC1918/ULA), link-local (incl. cloud
metadata 169.254.169.254), multicast, reserved, unspecified, benchmark, and
IPv4-mapped IPv6 forms of any blocked v4 range.

The DNS resolver is injectable so tests never touch the network and so a
future pinned-IP transport can reuse the same gate.
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from app.config.settings import Settings
from app.sources.career.errors import (
    InvalidCareerUrlError,
    SourceSSRFBlockedError,
    UnsupportedSchemeError,
)

Resolver = Callable[[str], Awaitable[list[str]]]

USER_AGENT = "jarvis-job-discovery/0.1"


def _blocked_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            reason = _blocked_reason(mapped)
            return f"ipv4_mapped_{reason}" if reason else None
    if ip == ipaddress.ip_address("169.254.169.254"):
        return "cloud_metadata"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified_address"
    if ip.is_private:
        # Covers RFC1918 for IPv4 and ULA fc00::/7 (+NAT64 64:ff9b::/96 in
        # recent Pythons). Checked after the specific labels above.
        return "private_ip"
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("198.18.0.0/15"):
        return "benchmark_range"
    return None


def _validate_ip_literal(host: str) -> list[str] | None:
    """Return [host] when it is an IP literal (validated), else None."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    reason = _blocked_reason(ip)
    if reason is not None:
        raise SourceSSRFBlockedError(
            f"destination address blocked ({reason})",
            reason=reason,
        )
    return [host]


async def default_resolver(hostname: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(hostname, None)
    return [info[4][0] for info in infos]


async def assert_public_host(
    host: str,
    *,
    resolver: Resolver | None = None,
) -> list[str]:
    literal = _validate_ip_literal(host.strip("[]"))
    addresses = literal if literal is not None else await (resolver or default_resolver)(host)
    validated: list[str] = []
    for raw in addresses:
        literal_check = _validate_ip_literal(raw)
        if literal_check:
            validated.extend(literal_check)
            continue
    return validated


def validate_url(url: str, *, allow_http: bool = False) -> urlsplit:
    """Validate scheme/netloc/port of a candidate URL.

    Correction #2: HTTP is rejected unless explicitly allowed; HTTPS->HTTP
    redirects are ALWAYS rejected by the fetcher's per-hop re-validation.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()

    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if not scheme:
        raise InvalidCareerUrlError("URL has no scheme", reason="invalid_url")
    if scheme not in allowed_schemes:
        if scheme == "http":
            raise UnsupportedSchemeError(
                "plain http is not allowed (https only)",
                reason="scheme_not_allowed",
            )
        raise UnsupportedSchemeError(
            f"scheme {scheme!r} is not allowed",
            reason="scheme_not_allowed",
        )

    if not parts.hostname:
        raise InvalidCareerUrlError("URL has no host", reason="invalid_url")
    if parts.username or parts.password:
        raise InvalidCareerUrlError(
            "credentials embedded in URL are not allowed",
            reason="invalid_url",
        )

    # Explicit ports are a redirect/port-scan manipulation vector: only the
    # https default may be spelled out; everything else (including :80 on
    # tolerated http) is blocked.
    port = parts.port
    if port is not None and port != 443:
        raise SourceSSRFBlockedError(
            f"port {port} is not allowed",
            reason="port_not_allowed",
        )
    return parts


async def validate_and_resolve(
    settings: Settings,
    url: str,
    *,
    resolver: Resolver | None = None,
) -> tuple[urlsplit, list[str]]:
    """Full pre-flight gate used by the fetcher for every hop."""
    parts = validate_url(url, allow_http=settings.career_allow_http)
    ips = await assert_public_host(parts.hostname or "", resolver=resolver)
    return parts, ips


__all__ = [
    "USER_AGENT",
    "Resolver",
    "assert_public_host",
    "default_resolver",
    "validate_and_resolve",
    "validate_url",
]
