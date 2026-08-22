"""Career-extractor data model: layered signal bag, provenance, results.

The orchestrator offers every extracted value into a :class:`SignalBag` in
strict precedence order (jsonld -> embedded -> dom -> meta -> url). The bag
keeps the FIRST offer per field and records every later, different-layer
offer as a conflict — conflicts are never silently resolved.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from app.models.job import Job
from app.sources.base import SourceError, SourceWarning

Layer = Literal["jsonld", "embedded", "dom", "meta", "url"]

#: Highest precedence first; offer order must match this tuple.
LAYER_PRECEDENCE: tuple[Layer, ...] = ("jsonld", "embedded", "dom", "meta", "url")

ExtractionStatus = Literal[
    "JOB_EXTRACTED",
    "NO_JOB_DETECTED",
    "FETCH_FAILED",
    "EXTRACTION_FAILED",
]


@dataclass(frozen=True)
class Claim:
    value: Any
    layer: Layer


@dataclass
class SignalBag:
    """First-writer-wins field store with explicit conflict recording."""

    _claims: dict[str, Claim] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def offer(self, field_name: str, layer: Layer, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        existing = self._claims.get(field_name)
        if existing is None:
            if isinstance(value, list) and not value:
                return
            self._claims[field_name] = Claim(value=value, layer=layer)
            return
        if existing.layer == layer:
            return  # same layer re-offering: keep first, not a cross-layer conflict
        self.conflicts.append(
            {
                "field": field_name,
                "winner_layer": existing.layer,
                "loser_layer": layer,
                "winner_value_preview": _preview(existing.value),
                "loser_value_preview": _preview(value),
            }
        )

    def get(self, field_name: str) -> Any:
        claim = self._claims.get(field_name)
        return claim.value if claim else None

    def layer_of(self, field_name: str) -> Layer | None:
        claim = self._claims.get(field_name)
        return claim.layer if claim else None

    def provenance(self) -> dict[str, str]:
        return {name: claim.layer for name, claim in sorted(self._claims.items())}

    def contains(self, field_name: str) -> bool:
        return field_name in self._claims

    def __contains__(self, field_name: str) -> bool:
        return self.contains(field_name)

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        return iter(self._claims.items())


def _preview(value: Any, limit: int = 80) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text[:limit]


@dataclass(frozen=True)
class ExtractionResult:
    """Structured outcome of one candidate-URL extraction.

    A page that is not a job yields NO_JOB_DETECTED with a machine-readable
    ``reason`` — never a bare "0 jobs found".
    """

    status: ExtractionStatus
    job: Job | None = None
    #: Machine-readable reason (e.g. insufficient_evidence,
    #: listing_page_detected, non_html, robots_disallowed).
    reason: str | None = None
    detail: str | None = None
    warnings: tuple[SourceWarning, ...] = ()
    errors: tuple[SourceError, ...] = ()
    final_url: str | None = None


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    etag: str | None = None
    last_modified: str | None = None


__all__ = [
    "Claim",
    "ExtractionResult",
    "ExtractionStatus",
    "FetchedPage",
    "LAYER_PRECEDENCE",
    "Layer",
    "SignalBag",
]
