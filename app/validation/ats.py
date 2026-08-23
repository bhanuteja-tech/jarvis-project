"""ATS compatibility checks A1–A8 (advisory; max severity WARN)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.dedup.normalize import base_normalize
from app.jdunderstanding.models import ExtractionStatus
from app.jdunderstanding.taxonomy import find_skill_hits
from app.validation.models import AtsMetrics, CheckResult, KeywordCount
from app.validation.resolver import gather_evidence_corpus

_ORDER: tuple[str, ...] = (
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
)

_STUFF_MIN_COUNT = 3
_STUFF_RATIO = 2.0


def _tailored_skill_names(tailored: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("name")).strip().lower()
        for item in tailored.get("skills") or []
        if item.get("name")
    }


def _coverage_pct(matched: int, total: int) -> float:
    if total <= 0:
        return 100.0  # not_requested counts as fully covered
    return round(100.0 * matched / total, 1)


def evaluate_ats(
    tailored_resume: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
    analysis: Mapping[str, Any] | None,
    match_result: Mapping[str, Any] | None,
) -> tuple[list[CheckResult], AtsMetrics]:
    checks: list[CheckResult] = []

    tailored_names = _tailored_skill_names(tailored_resume)
    tailored_text = "\n".join(
        str(value)
        for value in _flatten(tailored_resume)
        if isinstance(value, str)
    )
    corpus_text = "\n".join(
        str(value)
        for value in gather_evidence_corpus(candidate_profile)
    )

    # ---- A1/A2: required & preferred coverage -------------------------------
    jd_required: set[str] = set()
    jd_preferred: set[str] = set()
    if analysis is not None:
        skills_section = analysis.get("skills") or {}
        for item in skills_section.get("required") or []:
            name = item.get("name")
            if name:
                jd_required.add(str(name).strip().lower())
        for item in skills_section.get("preferred") or []:
            name = item.get("name")
            if name:
                jd_preferred.add(str(name).strip().lower())

    matched_required = jd_required & tailored_names
    matched_preferred = jd_preferred & tailored_names
    required_pct = _coverage_pct(len(matched_required), len(jd_required))
    preferred_pct = _coverage_pct(len(matched_preferred), len(jd_preferred))

    missing_from_match = [
        str(name).lower()
        for name in (match_result or {}).get("missing_required") or []
    ]
    unaddressed = tailored_resume.get("unaddressed_jd_requirements") or []

    a1_detail = (
        f"required skill coverage {required_pct}% "
        f"({len(matched_required)}/{len(jd_required)}); "
        f"missing: {', '.join(sorted(jd_required - tailored_names)) or 'none'}"
    )
    consistency_problem = any(
        name not in tailored_names and name not in unaddressed
        for name in missing_from_match
    ) or any(name.lower() not in missing_from_match for name in unaddressed)
    checks.append(
        CheckResult(
            "A1_required_skill_coverage",
            "warning" if consistency_problem else "passed",
            a1_detail + ("; inconsistent with match_result" if consistency_problem else ""),
        )
    )

    checks.append(
        CheckResult(
            "A2_preferred_skill_coverage", "passed",
            f"preferred skill coverage {preferred_pct}% "
            f"({len(matched_preferred)}/{len(jd_preferred)})",
        )
    )

    # ---- A3: responsibility token coverage ----------------------------------
    resp_tokens: set[str] = set()
    if analysis is not None:
        resp_section = analysis.get("responsibilities") or {}
        for item in resp_section.get("items") or []:
            text_value = item.get("text")
            if isinstance(text_value, str):
                resp_tokens |= {
                    token
                    for token in base_normalize(text_value).split()
                    if len(token) >= 3
                }
    tailored_tokens = {
        token for token in base_normalize(tailored_text).split() if len(token) >= 3
    }
    covered_resp = len(resp_tokens & tailored_tokens)
    resp_total = max(1, len(resp_tokens))
    responsibility_coverage = round(100.0 * covered_resp / resp_total, 1)
    checks.append(
        CheckResult(
            "A3_responsibility_token_coverage", "info",
            f"{covered_resp}/{resp_total} JD responsibility tokens appear in the "
            "tailored resume (informational)",
        )
    )

    # ---- A4/A5: keyword counts + stuffing ------------------------------------
    keyword_counts = _keyword_counts(corpus_text, tailored_text)

    stuffing_terms: list[str] = []
    for entry in keyword_counts:
        if (
            entry.tailored >= _STUFF_MIN_COUNT
            and entry.tailored > entry.original * _STUFF_RATIO
        ):
            stuffing_terms.append(entry.term)
    if stuffing_terms:
        checks.append(
            CheckResult(
                "A5_keyword_stuffing", "warning",
                "keyword stuffing suspected for: " + ", ".join(stuffing_terms[:8]),
            )
        )
    else:
        checks.append(
            CheckResult("A5_keyword_stuffing", "passed",
                        "no keyword stuffing detected")
        )

    # ---- A6: section order/presence -------------------------------------------
    present_order = [
        key for key in _ORDER if key in tailored_resume and tailored_resume[key]
    ]
    positions = [_ORDER.index(key) for key in present_order]
    if positions == sorted(positions):
        checks.append(
            CheckResult("A6_section_order", "passed",
                        "sections follow the canonical ordering")
        )
    else:
        checks.append(
            CheckResult("A6_section_order", "warning",
                        "section ordering deviates from the canonical sequence")
        )

    # ---- A7: format limits -----------------------------------------------------
    format_problems: list[str] = []
    max_highlights = 10
    for index, item in enumerate(tailored_resume.get("experience") or []):
        highlight_count = len(item.get("highlights") or [])
        if highlight_count > max_highlights:
            format_problems.append(
                f"experience[{index}] has {highlight_count} highlights"
            )
        for bullet in item.get("highlights") or []:
            final_text = bullet.get("final_text") or ""
            if len(final_text) > 300:
                format_problems.append(
                    f"experience[{index}] has an over-long bullet "
                    f"({len(final_text)} chars)"
                )
    total_chars = len(tailored_text)
    if total_chars > 50_000:
        format_problems.append(f"resume length {total_chars} exceeds guidance")

    if format_problems:
        checks.append(
            CheckResult("A7_format_limits", "warning",
                        "; ".join(format_problems[:5]))
        )
    else:
        checks.append(
            CheckResult("A7_format_limits", "passed",
                        "highlight caps and lengths within limits")
        )

    # ---- A8: date-range connector consistency -----------------------------------
    connectors: set[str] = set()
    for item in tailored_resume.get("experience") or []:
        date_range = item.get("date_range_raw")
        if isinstance(date_range, str) and re.search(r"\s[-–—]\s", date_range):
            for symbol in ("–", "—", "-"):
                if f" {symbol} " in date_range:
                    connectors.add(symbol)
    if len(connectors) > 1:
        checks.append(
            CheckResult("A8_date_range_consistency", "warning",
                        f"inconsistent range separators: {sorted(connectors)}")
        )
    else:
        checks.append(
            CheckResult("A8_date_range_consistency", "passed",
                        "consistent date-range separators")
        )

    metrics = AtsMetrics(
        required_coverage_pct=required_pct,
        preferred_coverage_pct=preferred_pct,
        responsibility_token_coverage_pct=responsibility_coverage,
        keyword_counts=sorted(keyword_counts,
                              key=lambda entry: (-entry.tailored, entry.term)),
    )
    return checks, metrics


def _keyword_counts(
    corpus_text: str, tailored_text: str
) -> list[KeywordCount]:
    original_hits: dict[str, int] = {}
    tailored_hits: dict[str, int] = {}

    for hit in find_skill_hits(corpus_text):
        original_hits[hit.canonical] = original_hits.get(hit.canonical, 0) + 1
    for hit in find_skill_hits(tailored_text):
        tailored_hits[hit.canonical] = tailored_hits.get(hit.canonical, 0) + 1

    entries: list[KeywordCount] = []
    for canonical_name in sorted(set(original_hits) | set(tailored_hits)):
        entries.append(
            KeywordCount(
                term=canonical_name,
                original=original_hits.get(canonical_name, 0),
                tailored=tailored_hits.get(canonical_name, 0),
            )
        )
    return entries


def _flatten(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _flatten(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _flatten(child)
    elif isinstance(value, str):
        yield value


__all__ = ["evaluate_ats"]
