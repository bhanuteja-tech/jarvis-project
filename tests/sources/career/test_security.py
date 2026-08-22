"""SSRF boundary: scheme/port/host-IP validation (pure, offline)."""

from __future__ import annotations

import pytest

from app.sources.career.errors import (
    InvalidCareerUrlError,
    SourceSSRFBlockedError,
    UnsupportedSchemeError,
)
from app.sources.career.security import assert_public_host, validate_and_resolve
from tests.support import make_settings


class TestValidateUrl:
    def test_https_accepted(self) -> None:
        parts = validate_url("https://jobs.example.com/x")
        assert parts.hostname == "jobs.example.com"

    @pytest.mark.parametrize(
        "bad_url",
        [
            "ftp://example.com/file",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/html,x",
            "mailto:x@example.com",
        ],
    )
    def test_non_http_schemes_rejected(self, bad_url: str) -> None:
        with pytest.raises(UnsupportedSchemeError):
            validate_url(bad_url)

    def test_http_rejected_by_default(self) -> None:
        with pytest.raises(UnsupportedSchemeError):
            validate_url("http://example.com/job")

    def test_http_allowed_with_explicit_flag(self) -> None:
        parts = validate_url("http://example.com/job", allow_http=True)
        assert parts.scheme == "http"

    def test_missing_scheme_invalid(self) -> None:
        with pytest.raises(InvalidCareerUrlError):
            validate_url("example.com/job")

    def test_missing_host_invalid(self) -> None:
        with pytest.raises(InvalidCareerUrlError):
            validate_url("https:///path")

    def test_embedded_credentials_rejected(self) -> None:
        with pytest.raises(InvalidCareerUrlError):
            validate_url("https://user:pass@example.com/job")

    def test_arbitrary_port_blocked(self) -> None:
        with pytest.raises(SourceSSRFBlockedError):
            validate_url("https://example.com:8443/job")

    def test_explicit_443_allowed(self) -> None:
        validate_url("https://example.com:443/job")

    def test_http_port_80_only_when_http_allowed(self) -> None:
        with pytest.raises(SourceSSRFBlockedError):
            validate_url("http://example.com:80/job", allow_http=True)


class TestIpGate:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "::1",
            "10.1.2.3",
            "172.16.0.9",
            "192.168.1.5",
            "169.254.169.254",
            "fe80::1",
            "fc00::1",
            "ff02::1",
            "240.0.0.1",
            "::",
            "::ffff:10.0.0.1",
            "::ffff:169.254.169.254",
            "198.18.0.7",
        ],
    )
    async def test_blocked_addresses_raise(self, ip: str) -> None:
        settings = make_settings()
        with pytest.raises(SourceSSRFBlockedError) as excinfo:
            await validate_and_resolve(settings, f"https://{ip}/job", resolver=None)
        assert excinfo.value.reason is not None

    async def test_public_literal_passes(self) -> None:
        settings = make_settings()
        _parts, ips = await validate_and_resolve(
            settings, "https://93.184.216.34/job", resolver=None
        )
        assert ips == ["93.184.216.34"]

    async def test_hostname_resolved_through_injected_resolver(self) -> None:
        from tests.support import fake_resolver

        settings = make_settings()
        resolver = fake_resolver({"internal.example": ["10.0.0.5"]})

        with pytest.raises(SourceSSRFBlockedError) as excinfo:
            await validate_and_resolve(
                settings, "https://internal.example/job", resolver=resolver
            )
        assert excinfo.value.reason == "private_ip"

    async def test_assert_public_host_returns_validated_ips(self) -> None:
        ips = await assert_public_host("example.com")
        assert ips  # default resolver ran; loopback not asserted here
