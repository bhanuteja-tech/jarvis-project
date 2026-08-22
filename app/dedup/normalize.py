"""Deterministic text normalization for deduplication keys.

Conservative by design: NFKC + casefold + accent stripping, whitespace
collapse, punctuation removal EXCEPT ``+ # &`` (C++, C#, AT&T survive),
legal-suffix stripping for companies, parenthetical removal and separator
collapse for titles, and a tiny explicit abbreviation map for locations.
Remote semantics are detected before normalization so
``remote``/``telecommute``/``wfh`` collapse to a single key while any city
name stays distinct.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s+#&]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_SEPARATORS_RE = re.compile(r"[-–—|/:]+")
_PARENS_RE = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_WORD_RE = re.compile(r"[a-z]+")

_COMPANY_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "gmbh", "corp",
        "corporation", "co", "company", "plc", "sa", "nv", "ag", "kg",
        "bv", "oy", "ab", "pte", "srl", "spa",
    }
)

_LOCATION_PHRASE_MAP: dict[str, str] = {
    "united states of america": "united states",
    "united states": "us",
    "new york city": "new york",
    "san francisco bay area": "san francisco",
    "washington d c": "washington",
    "nyc": "new york",
    "sf": "san francisco",
}

_REMOTE_TOKENS: frozenset[str] = frozenset(
    {"remote", "telecommute", "wfh", "anywhere"}
)
_REMOTE_PHRASES: tuple[str, ...] = ("work from home",)


def base_normalize(value: str) -> str:
    nfkd = unicodedata.normalize("NFKC", value).casefold()
    decomposed = "".join(
        ch for ch in unicodedata.normalize("NFD", nfkd) if not unicodedata.combining(ch)
    )
    no_punct = _PUNCT_RE.sub(" ", decomposed)
    return _WS_RE.sub(" ", no_punct).strip()


# Backwards-compatible alias used internally.
_base = base_normalize


def _drop_leading_article(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] == "the":
        return tokens[1:]
    return tokens


def _strip_trailing_suffixes(tokens: list[str]) -> list[str]:
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return tokens


def normalize_company(name: str) -> str:
    text = _base(name)
    tokens = [token for token in text.split() if token]
    tokens = _drop_leading_article(tokens)
    tokens = _strip_trailing_suffixes(tokens)
    return " ".join(tokens)


def normalize_title(title: str) -> str:
    without_parens = _PARENS_RE.sub(" ", title)
    with_separators = _SEPARATORS_RE.sub(" ", without_parens)
    return base_normalize(with_separators)


def is_remote_location(location: str) -> bool:
    lowered = location.casefold()
    tokens = set(_WORD_RE.findall(lowered))
    if tokens & _REMOTE_TOKENS:
        return True
    return any(phrase in lowered for phrase in _REMOTE_PHRASES)


def location_key(location: str | None) -> str | None:
    """Comparison key; the literal ``remote`` never equals a city."""
    if not isinstance(location, str):
        return None
    if is_remote_location(location):
        return "remote"
    text = base_normalize(_SEPARATORS_RE.sub(" ", location))
    for phrase in sorted(_LOCATION_PHRASE_MAP, key=len, reverse=True):
        pattern = r"\b" + re.escape(phrase) + r"\b"
        replacement = _LOCATION_PHRASE_MAP[phrase]
        text = re.sub(pattern, replacement, text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


__all__ = [
    "base_normalize",
    "is_remote_location",
    "location_key",
    "normalize_company",
    "normalize_title",
]
