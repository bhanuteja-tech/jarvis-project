"""Deterministic normalization behavior (dedup keys)."""

from __future__ import annotations

from app.dedup.normalize import (
    base_normalize,
    is_remote_location,
    location_key,
    normalize_company,
    normalize_title,
)


class TestBaseNormalize:
    def test_casefold_and_accents_collapse(self) -> None:
        assert base_normalize("Café Corp") == base_normalize("CAFE  corp")

    def test_punctuation_removed_but_plus_hash_ampersand_kept(self) -> None:
        assert base_normalize("at&t inc.") == "at&t inc"
        assert base_normalize("c++ dev.") == "c++ dev"
        assert base_normalize("c# role.") == "c# role"
        assert "." not in base_normalize("name corp.")

    def test_idempotent(self) -> None:
        once = base_normalize("Näme — With Punct!!uation")
        assert base_normalize(once) == once


class TestCompanyKey:
    def test_legal_suffixes_stripped(self) -> None:
        assert normalize_company("Acme Software Inc.") == normalize_company(
            "acme software"
        )

    def test_suffix_chain_collapses(self) -> None:
        assert normalize_company("Acme Co Ltd") == normalize_company("acme")

    def test_leading_article_dropped(self) -> None:
        assert normalize_company("The Boring Company") == normalize_company(
            "boring company"
        )


class TestTitleKey:
    def test_parenthetical_removed(self) -> None:
        assert normalize_title("Backend Engineer (Remote)") == normalize_title(
            "backend engineer"
        )

    def test_separators_collapse(self) -> None:
        assert normalize_title("Engineer - Platform | Backend") == (
            normalize_title("engineer platform backend")
        )

    def test_seniority_remains_distinct(self) -> None:
        """Mandated false-positive guard: seniority is a different job."""
        assert normalize_title("Senior Software Engineer") != normalize_title(
            "software engineer"
        )


class TestLocationKey:
    def test_remote_variants_share_key(self) -> None:
        variants = ["Remote", "Telecommute", "Work from home", "Anywhere"]
        keys = {location_key(variant) for variant in variants}
        assert keys == {"remote"}

    def test_remote_never_equals_city(self) -> None:
        assert location_key("Remote") != location_key("New York, NY")

    def test_micro_map_applies(self) -> None:
        assert location_key("NYC") == location_key("New York")
        assert (
            location_key("San Francisco, United States of America")
            == location_key("san francisco us")
        )

    def test_none_location_is_none(self) -> None:
        assert location_key(None) is None

    def test_is_remote_detection(self) -> None:
        assert is_remote_location("100% Remote friendly")
        assert not is_remote_location("Remotely located building, Austin TX")


def _base(value: str) -> str:  # local alias for readability of first test
    return base_normalize(value)
