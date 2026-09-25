"""Speech Normalization and Correction Extraction Engine for JARVIS.

Extracts explicit user corrections (e.g. "It's not BS code, open VS Code"),
normalizes speech-to-text acoustic corruptions, and strips natural language
filler prefixes to enable deterministic routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Patterns where the user explicitly negates a previous STT confusion or action
CORRECTION_PATTERNS = [
    # "it's not BS code, open VS code", "its not X, do Y"
    re.compile(
        r"^(?:it'?s\s+not|that'?s\s+not|not)\s+(?P<rejected>.+?)[,;:—\-]\s*(?P<corrected>.+)$",
        re.IGNORECASE,
    ),
    # "it's not BS code open VS code on my laptop" (no punctuation)
    re.compile(
        r"^(?:it'?s\s+not|that'?s\s+not|not)\s+(?P<rejected>.+?)\s+(?P<corrected>(?:open|launch|start|run|go\s+to|navigate|search|find|list|show|close|kill)\s+.+)$",
        re.IGNORECASE,
    ),
    # "no, open VS code", "no do Y"
    re.compile(
        r"^(?:no|nope|wait|cancel\s+that)[,;:—\-]?\s+(?:actually\s+|rather\s+|just\s+)?(?P<corrected>.+)$",
        re.IGNORECASE,
    ),
    # "i said open VS code", "i meant VS code"
    re.compile(
        r"^(?:i\s+said|i\s+meant|what\s+i\s+meant\s+was|i\s+actually\s+wanted)\s+(?P<corrected>.+)$",
        re.IGNORECASE,
    ),
    # "actually open VS code", "rather open VS code"
    re.compile(
        r"^(?:actually|rather|instead)\s+(?P<corrected>.+)$",
        re.IGNORECASE,
    ),
]

# Polite prefixes and filler phrases to strip cleanly
FILLER_PREFIXES = [
    r"^(?:can\s+you\s+(?:just\s+|please\s+)?|could\s+you\s+(?:just\s+|please\s+)?|would\s+you\s+(?:please\s+)?|please\s+|just\s+|jarvis\s*,?\s*)+",
    r"^(?:hey\s+jarvis\s*,?\s*|ok\s+jarvis\s*,?\s*)",
]

# Device/environment filler suffixes
DEVICE_SUFFIXES = [
    r"\s+(?:on|in)\s+my\s+(?:laptop|computer|pc|machine|desktop|system)$",
    r"\s+for\s+me$",
]

# Acoustic STT token replacements
ACOUSTIC_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbs\s+code\b", re.IGNORECASE), "vs code"),
    (re.compile(r"\bv\s+s\s+code\b", re.IGNORECASE), "vs code"),
    (re.compile(r"\bvisual\s+code\b", re.IGNORECASE), "visual studio code"),
    (re.compile(r"\bmicrosoft\s+h\b", re.IGNORECASE), "microsoft edge"),
    (re.compile(r"\bgoogle\s+chrome\s+browser\b", re.IGNORECASE), "google chrome"),
]


@dataclass(frozen=True)
class NormalizedTurn:
    """Result of speech normalization and correction extraction."""

    raw_text: str
    cleaned_text: str
    is_correction: bool
    rejected_target: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text,
            "is_correction": self.is_correction,
            "rejected_target": self.rejected_target,
            "confidence": self.confidence,
        }


def normalize_speech(text: str) -> NormalizedTurn:
    """Normalize input, detect corrections, and clean filler tokens."""
    raw = (text or "").strip()
    if not raw:
        return NormalizedTurn(raw_text="", cleaned_text="", is_correction=False)

    working = raw.strip()
    is_correction = False
    rejected: str | None = None

    # 1. Check for explicit correction patterns
    for pat in CORRECTION_PATTERNS:
        match = pat.match(working)
        if match:
            is_correction = True
            gd = match.groupdict()
            if "rejected" in gd and gd["rejected"]:
                rejected = gd["rejected"].strip()
            working = gd["corrected"].strip()
            break

    # 2. Strip polite / filler prefixes
    for prefix_pat in FILLER_PREFIXES:
        working = re.sub(prefix_pat, "", working, flags=re.IGNORECASE).strip()

    # 3. Apply acoustic STT normalizations
    for pat, repl in ACOUSTIC_REPLACEMENTS:
        working = pat.sub(repl, working)

    # 4. Strip device context suffixes if not part of a search query
    # E.g. "open VS code on my laptop" -> "open VS code"
    # But preserve "search my Desktop for resume"
    if not re.search(r"^(?:search|find|list|what\s+files)\b", working, re.IGNORECASE):
        for suffix_pat in DEVICE_SUFFIXES:
            working = re.sub(suffix_pat, "", working, flags=re.IGNORECASE).strip()

    cleaned = working.strip().strip(".?!")

    return NormalizedTurn(
        raw_text=raw,
        cleaned_text=cleaned,
        is_correction=is_correction,
        rejected_target=rejected,
        confidence=0.95 if is_correction else 1.0,
    )
