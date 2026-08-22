"""URL canonicalization policy (approved tracking/identity rules)."""

from __future__ import annotations

from app.sources.career.url_canon import canonicalize_url, canonicalize_with_declared


class TestCanonicalizeUrl:
    def test_tracking_parameters_removed(self) -> None:
        url = canonicalize_url(
            "https://jobs.example.com/x?utm_source=g&utm_medium=c&fbclid=zz&id=7"
        )
        assert url == "https://jobs.example.com/x?id=7"

    def test_utm_prefix_family_removed(self) -> None:
        url = canonicalize_url("https://jobs.example.com/x?utmx=1&utm_campaign=q&a=b")
        assert url == "https://jobs.example.com/x?a=b"

    def test_job_identity_query_keys_preserved(self) -> None:
        url = canonicalize_url("https://boards.example.com/jobs?gh_jid=456&ref=x")
        assert "gh_jid=456" in url

    def test_query_parameters_sorted(self) -> None:
        url = canonicalize_url("https://e.com/j?b=2&a=1")
        assert url == "https://e.com/j?a=1&b=2"

    def test_fragment_dropped(self) -> None:
        assert canonicalize_url("https://e.com/j#section") == "https://e.com/j"

    def test_trailing_slash_stripped_but_root_kept(self) -> None:
        assert canonicalize_url("https://e.com/jobs/") == "https://e.com/jobs"
        assert canonicalize_url("https://e.com/") == "https://e.com/"

    def test_default_https_port_stripped_and_explicit_kept(self) -> None:
        assert canonicalize_url("https://e.com:443/j") == "https://e.com/j"
        assert canonicalize_url("https://e.com:8443/j").endswith(":8443/j")

    def test_host_lowercased_www_preserved(self) -> None:
        assert (
            canonicalize_url("https://WWW.Example.COM/J")
            == "https://www.example.com/J"
        )

    def test_no_percent_renormalization_damage(self) -> None:
        url = "https://e.com/j/a%2Fb"
        assert "%2F" in canonicalize_url(url)


class TestDeclaredCanonical:
    def test_same_host_https_canonical_honored(self) -> None:
        final = "https://careers.example.com/jobs/ml-engineer-123"
        declared = "https://careers.example.com/jobs/ml-engineer-123?src=share"
        canon, honored = canonicalize_with_declared(final, declared)
        assert honored is True
        assert canon == "https://careers.example.com/jobs/ml-engineer-123"

    def test_cross_host_canonical_ignored(self) -> None:
        final = "https://careers.example.com/j"
        canon, honored = canonicalize_with_declared(final, "https://evil.org/j")
        assert honored is False
        assert canon.startswith("https://careers.example.com")

    def test_http_declared_canonical_ignored(self) -> None:
        final = "https://careers.example.com/j"
        canon, honored = canonicalize_with_declared(final, "http://careers.example.com/j")
        assert honored is False
