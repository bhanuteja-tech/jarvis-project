"""JSON-LD discovery and Schema.org JobPosting extraction.

Tolerant by contract:
- each ``<script type="application/ld+json">`` block parses independently;
  a malformed block is counted and skipped, never fatal;
- accepts a single object, a bare array, and ``@graph`` containers;
- only nodes whose ``@type`` includes ``JobPosting`` are collected; unrelated
  structured data (Organization/WebSite/BreadcrumbList) is counted, ignored;
- recursion is bounded (depth/nodes) so hostile payloads cannot explode.

Microdata/RDFa markup forms are deliberately not parsed in this phase
(documented plan decision).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_MAX_DEPTH = 6
_MAX_NODES = 500


@dataclass
class JsonLdStats:
    blocks_found: int = 0
    blocks_parsed: int = 0
    blocks_skipped: int = 0
    jobposting_nodes: int = 0
    other_nodes: int = 0
    skipped_block_previews: list[str] = field(default_factory=list)


def _is_jobposting(node: dict[str, Any]) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, str):
        return node_type.strip().lower() == "jobposting"
    if isinstance(node_type, list):
        return any(
            isinstance(t, str) and t.strip().lower() == "jobposting"
            for t in node_type
        )
    return False


def _walk(node: Any, depth: int, stats: JsonLdStats, out: list[dict[str, Any]]) -> None:
    if len(out) >= _MAX_NODES or depth > _MAX_DEPTH:
        return
    if isinstance(node, list):
        for item in node[:_MAX_NODES]:
            _walk(item, depth + 1, stats, out)
        return
    if not isinstance(node, dict):
        return
    if _is_jobposting(node):
        stats.jobposting_nodes += 1
        out.append(node)
        # Keep walking: @graph children of a JobPosting are unlikely but a
        # page may legitimately contain several independent postings.
    else:
        stats.other_nodes += 1

    graph = node.get("@graph")
    if graph is not None:
        _walk(graph, depth + 1, stats, out)


def extract_jobpostings(html: str) -> tuple[list[dict[str, Any]], JsonLdStats]:
    """Parse all JSON-LD blocks and collect JobPosting nodes."""
    stats = JsonLdStats()
    soup = BeautifulSoup(html, "html.parser")

    collected: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        stats.blocks_found += 1
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            stats.blocks_skipped += 1
            preview = raw.strip()[:60]
            stats.skipped_block_previews.append(preview)
            logger.warning(
                "malformed json-ld block skipped",
                extra={"source": "career_page", "operation": "jsonld", "error": str(exc)},
            )
            continue
        stats.blocks_parsed += 1
        _walk(data, 0, stats, collected)

    return collected, stats


def first_text(value: Any) -> str | None:
    """Coerce a schema.org value (Text | array-of-Text) to one stripped string."""
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, (str, int))), None)
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


__all__ = ["JsonLdStats", "extract_jobpostings", "first_text"]
