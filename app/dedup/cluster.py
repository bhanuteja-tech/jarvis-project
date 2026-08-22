"""Union-Find clustering with deterministic canonical-record selection.

Design (approved, Option B):
- Tier-0 batch collapse on ``(source, source_job_id)`` (newest fetched_at wins).
- R1 unions via global url-key buckets (complete).
- R2 unions via global ``(company_key, title_key)`` buckets (complete; location
  compatibility is a pairwise guard, so a missing location never blocks).
- R3 fuzzy pass runs only within company buckets and is hard-capped: beyond
  ``MAX_BUCKET_PAIRWISE`` members the fuzzy pass for that bucket is skipped
  with an explicit warning (exact tiers always complete). This bounds work
  without any global O(N^2) comparison.
- Canonical record = highest source rank -> most complete -> earliest
  discovered_at -> lexicographic identity.
- Merge semantics are FILL-NOT-OVERWRITE; every member keeps provenance in
  the winner's ``extra.sources[]``.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.dedup.matcher import decide, make_view

logger = logging.getLogger(__name__)

SOURCE_RANK: dict[str, int] = {
    "career_page": 4,
    "greenhouse": 3,
    "lever": 2,
    "searchapi": 1,
}
_RULE_PRIORITY: dict[str, int] = {
    "R1_url_key": 3,
    "R2_exact_keys": 2,
    "R3_title_fuzzy": 1,
}
_MAX_POTENTIAL_WARNINGS = 50
_MAX_BUCKET_PAIRWISE = 2000

_FILL_FIELDS: tuple[str, ...] = (
    "title",
    "company",
    "location",
    "description",
    "requirements",
    "responsibilities",
    "employment_type",
    "job_url",
    "apply_url",
)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        low, high = min(ra, rb), max(ra, rb)
        self._parent[high] = low  # smallest index becomes root: deterministic
        return True


@dataclass(frozen=True)
class DedupOutcome:
    jobs: list[dict[str, Any]]
    warnings: list[dict[str, str]]
    stats: dict[str, int]


def _completeness(job: Mapping[str, Any]) -> int:
    return sum(1 for name in _FILL_FIELDS if job.get(name) not in (None, ""))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _select_winner(
    views: list[Any], members: list[int], jobs: list[Mapping[str, Any]]
) -> int:
    def sort_key(idx: int) -> tuple[int, int, str, str, str]:
        view = views[idx]
        job = jobs[idx]
        discovered = job.get("discovered_at") or ""
        completeness = _completeness(job)
        return (
            -SOURCE_RANK.get(view.source, 0),
            -completeness,
            discovered,
            view.source,
            view.source_job_id,
        )

    return min(members, key=sort_key)


def _ordered_members(
    views: list[Any], members: list[int]
) -> list[int]:
    def key(idx: int) -> tuple[int, str, str]:
        view = views[idx]
        return (-SOURCE_RANK.get(view.source, 0), view.source, view.source_job_id)

    return sorted(members, key=key)


def _build_merged(
    jobs: list[Mapping[str, Any]],
    views: list[Any],
    members: list[int],
    winner_index: int,
    cluster_rule: str,
    vetoes: set[str],
) -> dict[str, Any]:
    ordered = [winner_index] + [
        idx for idx in _ordered_members(views, members) if idx != winner_index
    ]

    merged = copy.deepcopy(dict(jobs[winner_index]))
    merged["extra"] = copy.deepcopy(dict(jobs[winner_index].get("extra") or {}))

    for other_idx in ordered[1:]:
        other = jobs[other_idx]
        for field_name in _FILL_FIELDS:
            if merged.get(field_name) in (None, ""):
                value = other.get(field_name)
                if value not in (None, ""):
                    merged[field_name] = copy.deepcopy(value)
        if merged.get("salary") is None and other.get("salary") is not None:
            merged["salary"] = copy.deepcopy(other["salary"])

    for date_field in ("source_created_at", "source_updated_at"):
        candidates = [
            parsed
            for parsed in (_parse_datetime(jobs[idx].get(date_field)) for idx in ordered)
            if parsed is not None
        ]
        if candidates:
            earliest = min(candidates)
            merged[date_field] = earliest.isoformat()

    sources = []
    for idx in ordered:
        job = jobs[idx]
        sources.append(
            {
                "source": job.get("source"),
                "source_job_id": job.get("source_job_id"),
                "job_url": job.get("job_url"),
                "apply_url": job.get("apply_url"),
                "discovered_at": job.get("discovered_at"),
                "fetched_at": job.get("fetched_at"),
            }
        )
    dedup_extra: dict[str, Any] = {
        "winner_source": jobs[winner_index].get("source"),
        "rule": cluster_rule,
        "cluster_size": len(members),
        "members": [
            {"source": jobs[idx].get("source"), "source_job_id": jobs[idx].get("source_job_id")}
            for idx in sorted(members)
            if idx != winner_index
        ],
    }
    if vetoes:
        dedup_extra["vetoes"] = sorted(vetoes)

    existing_extra = merged.get("extra")
    extra = existing_extra if isinstance(existing_extra, dict) else {}
    extra.update({"dedup": dedup_extra, "sources": sources})
    merged["extra"] = extra
    return merged


def dedupe_jobs(jobs: list[Mapping[str, Any]]) -> DedupOutcome:
    total = len(jobs)
    views = [make_view(job, index) for index, job in enumerate(jobs)]
    uf = _UnionFind(total)
    active = [True] * total
    comparisons = 0
    pair_decisions: dict[tuple[int, int], Any] = {}
    veto_reasons: dict[frozenset[int], set[str]] = {}

    # --- Tier 0: batch-level collapse of identical source identities ---
    tier0: dict[tuple[str, str], int] = {}
    for index in range(total):
        view = views[index]
        key = (view.source, view.source_job_id)
        previous = tier0.get(key)
        if previous is None:
            tier0[key] = index
            continue
        newer_is_current = (jobs[index].get("fetched_at") or "") >= (
            jobs[previous].get("fetched_at") or ""
        )
        keep, drop = (index, previous) if newer_is_current else (previous, index)
        active[drop] = False
        tier0[key] = keep

    live_indices = [index for index in range(total) if active[index]]

    # --- R1: exact canonical URL keys ---
    url_buckets: dict[str, list[int]] = {}
    for index in live_indices:
        url_key = views[index].url_key
        if url_key is not None:
            url_buckets.setdefault(url_key, []).append(index)
    strongest_rule: dict[int, str] = {}

    for bucket in url_buckets.values():
        anchor = bucket[0]
        for other in bucket[1:]:
            comparisons += 1
            uf.union(anchor, other)
            rule = "R1_url_key"
            for member in (anchor, other):
                current_root = uf.find(member)
                if _RULE_PRIORITY[rule] > _RULE_PRIORITY.get(
                    strongest_rule.get(current_root, ""), 0
                ):
                    strongest_rule[current_root] = rule

    def apply_pair(i: int, j: int) -> None:
        nonlocal comparisons
        pair_key = (min(i, j), max(i, j))
        decision = pair_decisions.get(pair_key)
        if decision is None:
            comparisons += 1
            decision = decide(views[i], views[j])
            pair_decisions[pair_key] = decision
        else:
            return  # already evaluated once; deterministic result

        if decision.merged:
            uf.union(i, j)
            priority = _RULE_PRIORITY.get(decision.rule or "", 0)
            for member in (i, j):
                root = uf.find(member)
                if priority > _RULE_PRIORITY.get(strongest_rule.get(root, ""), 0):
                    strongest_rule[root] = decision.rule or ""
        elif decision.veto_reason:
            group = veto_reasons.setdefault(frozenset({i, j}), set())
            group.add(decision.veto_reason)

    # --- R2: exact company+title keys (location compatibility is a guard) ---
    exact_buckets: dict[tuple[str, str], list[int]] = {}
    for index in live_indices:
        view = views[index]
        if not view.company_key or not view.title_key:
            continue
        exact_buckets.setdefault((view.company_key, view.title_key), []).append(index)
    for bucket in exact_buckets.values():
        for position, left in enumerate(bucket):
            for right in bucket[position + 1:]:
                apply_pair(left, right)

    # --- R3: bounded fuzzy pass inside company buckets ---
    company_buckets: dict[str, list[int]] = {}
    truncated_buckets = 0
    for index in live_indices:
        company_key = views[index].company_key
        if company_key:
            company_buckets.setdefault(company_key, []).append(index)

    for company_bucket in company_buckets.values():
        if len(company_bucket) > _MAX_BUCKET_PAIRWISE:
            truncated_buckets += 1
            continue
        for position, left in enumerate(company_bucket):
            for right in company_bucket[position + 1:]:
                if uf.find(left) == uf.find(right):
                    continue  # same cluster already; skip redundant comparison
                apply_pair(left, right)

    warnings: list[dict[str, str]] = []
    candidate_pairs = sorted(
        (
            pair
            for pair, decision in pair_decisions.items()
            if decision.candidate and not decision.merged
        ),
        key=lambda pair: pair,
    )
    emitted = 0
    for left, right in candidate_pairs:
        decision = pair_decisions[(left, right)]
        message = (
            f"possible duplicate not auto-merged "
            f"({views[left].source}:{views[left].source_job_id} vs "
            f"{views[right].source}:{views[right].source_job_id}); "
            f"reason={decision.veto_reason}"
        )
        if emitted < _MAX_POTENTIAL_WARNINGS:
            warnings.append(
                {"code": "potential_duplicate", "message": message, "source": "dedup"}
            )
        elif emitted == _MAX_POTENTIAL_WARNINGS:
            warnings.append(
                {
                    "code": "potential_duplicate_truncated",
                    "message": "additional potential duplicates suppressed",
                    "source": "dedup",
                }
            )
        emitted += 1

    clusters: dict[int, list[int]] = {}
    for index in range(total):
        if not active[index]:
            continue
        clusters.setdefault(uf.find(index), []).append(index)

    results: list[tuple[int, dict[str, Any]]] = []
    clusters_merged = 0
    for _, members in sorted(clusters.items()):
        winner_index = _select_winner(views, members, jobs)
        if len(members) == 1:
            results.append((winner_index, copy.deepcopy(dict(jobs[winner_index]))))
            continue
        clusters_merged += 1
        root = uf.find(winner_index)
        cluster_rule = strongest_rule.get(root) or "R2_exact_keys"

        cluster_vetoes: set[str] = set()
        members_set = set(members)
        for pair, reasons in veto_reasons.items():
            if pair <= members_set:
                cluster_vetoes |= reasons

        merged = _build_merged(
            jobs, views, members, winner_index, cluster_rule, cluster_vetoes
        )
        results.append((winner_index, merged))

    results.sort(key=lambda item: item[0])
    final_jobs = [job for _, job in results]

    logger.info(
        "dedup complete",
        extra={
            "source": "dedup",
            "operation": "dedupe_jobs",
            "input_records": total,
            "output_records": len(final_jobs),
            "clusters_merged": clusters_merged,
            "comparisons": comparisons,
        },
    )
    return DedupOutcome(
        jobs=final_jobs,
        warnings=warnings,
        stats={
            "input_records": total,
            "output_records": len(final_jobs),
            "clusters_merged": clusters_merged,
            "comparisons": comparisons,
            "truncated_buckets": truncated_buckets,
        },
    )


__all__ = ["DedupOutcome", "dedupe_jobs"]
