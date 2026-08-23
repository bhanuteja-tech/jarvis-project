"""Canonical Phase 1–6 workflow node ordering and safe activity labels.

The Jarvis orchestrator derives ``workflow_node_started`` events from this
ordering (LangGraph ``updates`` streaming reports completions; starts are
derived deterministically from the known sequence). Labels are the ONLY
workflow internals exposed to users — never internal reasoning.
"""

from __future__ import annotations

#: Execution order of the discovery branch (candidate branch runs in
#: parallel and contains a single node).
CANONICAL_ORDER: tuple[str, ...] = (
    "fetch_sources",
    "deduplicate_jobs",
    "rank_jobs",
    "analyze_jd",
    "match_candidate_to_jobs",
    "tailor_resume",
    "validate_resume",
)

#: Parallel branch heads (both start immediately).
BRANCH_HEADS: tuple[str, ...] = ("fetch_sources", "build_candidate_profile")

_SUCCESSORS: dict[str, tuple[str, ...]] = {
    "fetch_sources": ("deduplicate_jobs",),
    "deduplicate_jobs": ("rank_jobs",),
    "rank_jobs": ("analyze_jd",),
    "analyze_jd": ("match_candidate_to_jobs",),
    "match_candidate_to_jobs": ("tailor_resume",),
    "tailor_resume": ("validate_resume",),
    "validate_resume": (),
}

#: Safe user-facing labels — NEVER internal reasoning.
LABELS: dict[str, str] = {
    "fetch_sources": "Searching jobs",
    "build_candidate_profile": "Building candidate profile",
    "deduplicate_jobs": "Removing duplicate jobs",
    "rank_jobs": "Ranking relevant jobs",
    "analyze_jd": "Analyzing job requirements",
    "match_candidate_to_jobs": "Matching candidate",
    "tailor_resume": "Tailoring resume",
    "validate_resume": "Validating resume",
}


def successors(node: str) -> tuple[str, ...]:
    return _SUCCESSORS.get(node, ())


def derive_next_starts(
    completed_nodes: set[str], already_started: set[str]
) -> list[str]:
    """Nodes whose predecessors have ALL completed and that have not started."""
    out: list[str] = []
    for node in CANONICAL_ORDER:
        if node in already_started or node in completed_nodes:
            continue
        predecessors = [
            candidate
            for candidate, successors in _SUCCESSORS.items()
            if node in successors
        ]
        if predecessors and all(p in completed_nodes for p in predecessors):
            out.append(node)
        elif not predecessors and node in BRANCH_HEADS:
            out.append(node)
    return out


__all__ = [
    "BRANCH_HEADS",
    "CANONICAL_ORDER",
    "LABELS",
    "derive_next_starts",
    "successors",
]
