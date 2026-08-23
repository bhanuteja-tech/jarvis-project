"""Taxonomy boundary safety: the mandated false-match pairs."""

from __future__ import annotations

import pytest

from app.jdunderstanding.taxonomy import find_skill_hits


def canonical_names(text: str) -> set[str]:
    return {hit.canonical for hit in find_skill_hits(text)}


class TestMandatedBoundaryPairs:
    @pytest.mark.parametrize(
        ("text", "must_include", "must_exclude"),
        [
            ("Experience with Java and JavaScript", "javascript", None),
            ("JavaScript required", "javascript", "java"),
            ("Strong C skills; C++ a plus", "c", None),
            ("C++ and C#", "c++", None),
            ("SQL plus NoSQL exposure", "sql", None),
            ("React and React Native apps", "react native", None),
            ("Write Pythonic code", None, "python"),
        ],
    )
    def test_pairs(self, text: str, must_include: str | None, must_exclude: str | None) -> None:
        names = canonical_names(text)

        if must_include:
            assert must_include in names
        if must_exclude:
            assert must_exclude not in names

    def test_java_alone_matches_java(self) -> None:
        assert "java" in canonical_names("Java backend services")

    def test_react_native_suppresses_plain_react(self) -> None:
        names = canonical_names("We build React Native mobile apps")
        # React Native claims the span; bare React must not double-count.
        assert "react" not in names
        assert "react native" in names

    def test_alias_resolution(self) -> None:
        assert "kubernetes" in canonical_names("K8s on AWS")
        assert "postgresql" in canonical_names("Postgres database")
        assert "google cloud platform" in canonical_names("GCP")

    def test_spans_are_verbatim(self) -> None:
        hits = find_skill_hits("PyTorch experience")
        assert hits[0].matched_as.lower() == "pytorch"
