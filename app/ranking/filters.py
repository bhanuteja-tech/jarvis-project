"""Hard-requirement filtering.

Missing/unknown job data NEVER eliminates a job (locked principle); it is
recorded as an evidence gap. Only positive, verified mismatches reject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.dedup.normalize import base_normalize, normalize_company
from app.ranking.features import JobFeatures
from app.ranking.preferences import HardRequirements


@dataclass(frozen=True)
class FilterOutcome:
    passed: bool
    failed_reason: str | None = None
    gaps: tuple[str, ...] = field(default_factory=tuple)


def apply_hard_filters(
    features: JobFeatures,
    hard: HardRequirements,
    *,
    now: datetime | None = None,
) -> FilterOutcome:
    gaps: list[str] = []

    for excluded in hard.exclude_companies:
        excluded_key = normalize_company(excluded)
        if features.company_key and features.company_key == excluded_key:
            return FilterOutcome(False, "excluded_company", _gaps(gaps))

    haystack_text = " ".join(token for part in features.skill_parts for token in part.tokens)
    for keyword in hard.exclude_keywords:
        pattern = r"\b" + re.escape(base_normalize(keyword).replace(" ", r"\b ")) + r"\b"
        if re.search(pattern, haystack_text):
            return FilterOutcome(False, "excluded_keyword", _gaps(gaps))

    if hard.locations:
        if not features.location_known:
            gaps.append("location")
        else:
            requested_keys = {base_normalize(location) for location in hard.locations}
            job_key = features.location_key or ""
            job_key_normalized = base_normalize(job_key)
            matched = any(
                job_key == requested or job_key_normalized == requested
                for requested in requested_keys
            )
            # remote semantics: a requested city never matches a remote job.
            if not matched:
                return FilterOutcome(False, "location_mismatch", _gaps(gaps))

    if hard.employment_types and features.employment is None:
        gaps.append("employment_type")
    elif hard.employment_types and features.employment not in hard.employment_types:
        return FilterOutcome(False, "employment_type_mismatch", _gaps(gaps))

    if hard.experience_levels and features.level is None:
        gaps.append("experience_level")
    elif hard.experience_levels and features.level not in hard.experience_levels:
        return FilterOutcome(False, "experience_level_mismatch", _gaps(gaps))

    if hard.max_age_hours is not None:
        reference = now or datetime.now().astimezone()
        if features.created_at is None:
            gaps.append("freshness_unknown")
        else:
            age_hours = (reference - features.created_at).total_seconds() / 3600.0
            if age_hours > hard.max_age_hours:
                return FilterOutcome(False, "too_old", _gaps(gaps))

    return FilterOutcome(True, None, _gaps(gaps))


def _gaps(gaps: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(gaps))


__all__ = ["FilterOutcome", "apply_hard_filters"]
