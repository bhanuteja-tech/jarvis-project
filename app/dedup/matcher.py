"""Pairwise matching rules R1-R3 and false-positive guards V1-V5.

Rules (approved):
- R1: job_url comparison keys equal -> merge (guards intentionally bypassed:
  the URL is the posting).
- R2: normalized company + title + location keys all equal (missing side
  tolerated) + guards pass.
- R3: title token-Jaccard >= 0.8 + company_key equal + location_key equal +
  guards pass.

Guards veto Tier B/C merges only (never R1) and each failing candidate pair
is flagged so the cluster layer can emit ONE meaningful potential_duplicate
warning per high-similarity non-merge — never one per comparison.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.dedup.normalize import (
    location_key,
    normalize_company,
    normalize_title,
)
from app.dedup.url_key import job_url_key

TITLE_JACCARD_THRESHOLD = 0.8
DESCRIPTION_RATIO_THRESHOLD = 0.85
_DESCRIPTION_MIN_CHARS = 120
_DESCRIPTION_CAP = 4000

_SLUG_DIGITS_RE = re.compile(r"-(\d{3,})(?:$|[/?#])")
_REQUISITION_QUERY_KEYS: frozenset[str] = frozenset(
    {"gh_jid", "jid", "job", "jobid", "ashby_jid", "posting_id"}
)


@dataclass(frozen=True)
class Decision:
    merged: bool
    rule: str | None = None
    #: Set when a blocking/high-similarity candidate failed a guard.
    veto_reason: str | None = None
    #: High-similarity candidate that ultimately did not merge.
    candidate: bool = False


@dataclass(frozen=True)
class JobView:
    index: int
    source: str
    source_job_id: str
    url_key: str | None
    company_key: str | None
    title_key: str | None
    title_tokens: frozenset[str]
    location_key: str | None
    employment_type: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    description: str | None
    id_signals: Mapping[str, str] = field(default_factory=dict)


def _id_signals(job: Mapping[str, Any]) -> dict[str, str]:
    """Structured requisition signals comparable across records."""
    signals: dict[str, str] = {}
    extra = job.get("extra") or {}

    jsonld_identifier = extra.get("jsonld_identifier")
    if isinstance(jsonld_identifier, str) and jsonld_identifier.strip():
        signals["schemaorg"] = jsonld_identifier.strip()

    # Generic type (no source prefix): different requisitions at the same
    # company must conflict even when discovered via different sources.
    internal_job_id = extra.get("internal_job_id")
    if internal_job_id not in (None, ""):
        signals["internal"] = str(internal_job_id)

    from urllib.parse import parse_qsl, urlsplit

    url = job.get("job_url") or ""
    for key, value in parse_qsl(urlsplit(str(url)).query, keep_blank_values=True):
        if key.lower() in _REQUISITION_QUERY_KEYS and value.strip():
            signals[f"query:{key.lower()}"] = value.strip()

    match = _SLUG_DIGITS_RE.search(urlsplit(str(url)).path or "")
    if match:
        signals.setdefault("slug_digits", match.group(1))

    return signals


def _salary_fields(job: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    """Accept both dict-form (state shape) and Salary value objects."""
    salary = job.get("salary")
    if isinstance(salary, Mapping):
        return (
            salary.get("min_amount"),
            salary.get("max_amount"),
            salary.get("currency"),
        )
    if salary is None:
        return None, None, None
    return salary.min_amount, salary.max_amount, salary.currency


def make_view(job: Mapping[str, Any], index: int) -> JobView:
    title_key = normalize_title(job.get("title") or "")
    description = job.get("description")
    salary_min, salary_max, salary_currency = _salary_fields(job)

    return JobView(
        index=index,
        source=job.get("source") or "",
        source_job_id=job.get("source_job_id") or "",
        url_key=job_url_key(job),
        company_key=normalize_company(job.get("company") or ""),
        title_key=title_key,
        title_tokens=frozenset(title_key.split()),
        location_key=location_key(job.get("location")),
        employment_type=(
            str(job.get("employment_type")).strip().lower()
            if isinstance(job.get("employment_type"), str)
            else None
        ),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        description=description if isinstance(description, str) else None,
        id_signals=_id_signals(job),
    )


def _title_jaccard(a: JobView, b: JobView) -> float:
    if not a.title_tokens or not b.title_tokens:
        return 0.0
    union = a.title_tokens | b.title_tokens
    return len(a.title_tokens & b.title_tokens) / len(union)


def _description_ratio(a: JobView, b: JobView) -> float:
    da, db = a.description, b.description
    if (
        da is None
        or db is None
        or len(da) < _DESCRIPTION_MIN_CHARS
        or len(db) < _DESCRIPTION_MIN_CHARS
    ):
        return -1.0  # guard not applicable
    capped_a = da[:_DESCRIPTION_CAP]
    capped_b = db[:_DESCRIPTION_CAP]
    return SequenceMatcher(None, capped_a, capped_b).ratio()


def _ids_conflict(a: JobView, b: JobView) -> bool:
    shared_types = set(a.id_signals) & set(b.id_signals)
    return any(a.id_signals[t] != b.id_signals[t] for t in shared_types)


def _types_conflict(a: JobView, b: JobView) -> bool:
    if a.employment_type is None or b.employment_type is None:
        return False
    return a.employment_type != b.employment_type


def _salary_disjoint(a: JobView, b: JobView) -> bool:
    if a.salary_min is None and a.salary_max is None:
        return False
    if b.salary_min is None and b.salary_max is None:
        return False
    if (a.salary_currency or "").upper() != (b.salary_currency or "").upper():
        return True  # different currencies: conservatively disjoint
    a_low = a.salary_min if a.salary_min is not None else float("-inf")
    a_high = a.salary_max if a.salary_max is not None else float("inf")
    b_low = b.salary_min if b.salary_min is not None else float("-inf")
    b_high = b.salary_max if b.salary_max is not None else float("inf")
    return a_high < b_low or b_high < a_low


def _first_veto_without_location(a: JobView, b: JobView) -> str | None:
    if _ids_conflict(a, b):
        return "V1_requisition_id_conflict"
    if _types_conflict(a, b):
        return "V3_employment_type_conflict"
    if _salary_disjoint(a, b):
        return "V4_salary_disjoint"
    ratio = _description_ratio(a, b)
    if ratio != -1.0 and ratio < DESCRIPTION_RATIO_THRESHOLD:
        return "V5_description_dissimilar"
    return None


def decide(a: JobView, b: JobView) -> Decision:
    # R1: identical posting URL is authoritative; guards deliberately bypassed.
    if a.url_key is not None and a.url_key == b.url_key:
        return Decision(merged=True, rule="R1_url_key")

    same_company = bool(a.company_key) and a.company_key == b.company_key
    if not same_company:
        return Decision(merged=False)

    title_equal = bool(a.title_key) and a.title_key == b.title_key
    jaccard = _title_jaccard(a, b)
    similar = title_equal or jaccard >= TITLE_JACCARD_THRESHOLD

    location_conflict = (
        a.location_key is not None
        and b.location_key is not None
        and a.location_key != b.location_key
    )

    if not similar:
        return Decision(merged=False)

    if location_conflict:
        # High-similarity pair (same company + compatible title) that differs
        # only by location: labeled veto, never a silent non-merge.
        return Decision(
            merged=False, veto_reason="V2_location_mismatch", candidate=True
        )

    veto = _first_veto_without_location(a, b)
    if veto is not None:
        return Decision(merged=False, veto_reason=veto, candidate=True)

    rule = "R2_exact_keys" if title_equal else "R3_title_fuzzy"
    return Decision(merged=True, rule=rule)


__all__ = [
    "Decision",
    "JobView",
    "decide",
    "make_view",
]
