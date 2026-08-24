"""Robust JSON extraction for LLM structured outputs.

Providers occasionally wrap JSON in markdown fences or prose. This helper
finds the first balanced JSON object and parses it; anything else returns
None so callers fall back safely.
"""

from __future__ import annotations

import json
from typing import Any


def parse_intent_json(raw: str) -> Any:
    """Extract the first JSON object from a raw completion (or None)."""
    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    # Fast path: the whole completion is JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip a single markdown fence pair if present.
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text.split("```", 1)[0]

    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            ch = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


__all__ = ["parse_intent_json"]
