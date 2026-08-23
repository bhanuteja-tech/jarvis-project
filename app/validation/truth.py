"""Truth checks T1–T10 (read-only; failures FAIL the overall report)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.dedup.normalize import base_normalize, informative_tokens
from app.jdunderstanding.taxonomy import find_skill_hits
from app.validation.models import CheckResult
from app.validation.resolver import (
    collect_evidence_refs,
    gather_evidence_corpus,
    resolve_path,
)


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?"
)


def _tokens(text: str) -> set[str]:
    """Informative tokens — shared lexicon with the Phase 5 truth guard."""
    return informative_tokens(text)


def _iter_tailored_texts(tailored: Mapping[str, Any]) -> list[tuple[str, str]]:
    """(field_label, text) pairs for every free-text surface in the artifact."""
    pairs: list[tuple[str, str]] = []
    summary = tailored.get("summary") or {}
    if isinstance(summary.get("text"), str) and summary["text"].strip():
        pairs.append(("summary.text", summary["text"]))
    for index, item in enumerate(tailored.get("experience") or []):
        if not isinstance(item, Mapping):
            continue
        for bullet in item.get("highlights") or []:
            if not isinstance(bullet, Mapping):
                continue
            final_text = bullet.get("final_text")
            if isinstance(final_text, str) and final_text.strip():
                bullet_ref = bullet.get("evidence_ref") or ""
                pairs.append((f"experience[{index}].{bullet_ref}", final_text))
    return pairs


def _check_containment(tailored: Mapping[str, Any], profile: Mapping[str, Any]) -> CheckResult:
    # Set-containment (content ⊆ candidate evidence): repetition is not
    # fabrication — frequency inflation is A5 keyword-stuffing's concern.
    allowed = set(_tokens(" ".join(gather_evidence_corpus(profile))))
    unsupported: list[str] = []
    checked = 0
    for field_label, text in _iter_tailored_texts(tailored):
        checked += 1
        used = _tokens(text)
        over = [token for token in used if token not in allowed]
        if over:
            unsupported.extend(f"{field_label}:{token}" for token in over[:5])
    if unsupported:
        return CheckResult(
            "T1_token_containment",
            "failed",
            f"unsupported tokens not present in candidate evidence: {', '.join(unsupported[:8])}",
        )
    return CheckResult(
        "T1_token_containment",
        "passed",
        f"{checked} tailored text surface(s) contained within candidate evidence",
    )


def _check_original_fidelity(
    tailored: Mapping[str, Any], profile: Mapping[str, Any]
) -> CheckResult:
    problems: list[str] = []
    for index, item in enumerate(tailored.get("experience") or []):
        for bullet in item.get("highlights") or []:
            original = bullet.get("original_text")
            final_text = bullet.get("final_text")
            evidence_ref = bullet.get("evidence_ref")

            # original must match the candidate highlight verbatim.
            found, value = resolve_path(profile, evidence_ref or "")
            if not found or not isinstance(value, str):
                problems.append(f"unresolvable original ref {evidence_ref!r}")
            elif value.strip() != str(original).strip():
                problems.append(f"original drift at experience[{index}]")

            # rewrites must themselves be contained.
            if (
                isinstance(final_text, str)
                and final_text != original
                and not _check_containment(
                    {"summary": {}, "experience": [{"highlights": [final_text]}]},
                    profile,
                ).status
                == "passed"
            ):
                problems.append(f"rewrite not contained at experience[{index}]")
    if problems:
        return CheckResult(
            "T2_original_fidelity",
            "failed",
            "; ".join(problems[:6]),
        )
    return CheckResult(
        "T2_original_fidelity",
        "passed",
        "all originals verbatim; rewrites contained",
    )


def _check_evidence_refs_resolvable(
    tailored: Mapping[str, Any], profile: Mapping[str, Any]
) -> CheckResult:
    refs = collect_evidence_refs(tailored)
    unresolved: list[str] = []
    for ref in refs:
        found, _value = resolve_path(profile, ref)
        if not found:
            unresolved.append(ref)
    if unresolved:
        return CheckResult(
            "T3_evidence_refs_resolvable",
            "failed",
            f"unresolved evidence refs: {', '.join(unresolved[:5])}",
        )
    return CheckResult(
        "T3_evidence_refs_resolvable",
        "passed",
        f"{len(refs)} evidence ref(s) resolved against the candidate profile",
    )


def _skill_names(tailored: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("name")).strip().lower()
        for item in tailored.get("skills") or []
        if item.get("name")
    }


def _check_no_fabricated_skills(
    tailored: Mapping[str, Any],
    profile: Mapping[str, Any],
    analysis: Mapping[str, Any] | None,
) -> CheckResult:
    candidate_names: set[str] = {
        str(item.get("name")).strip().lower()
        for item in (profile.get("skills") or {}).get("items") or []
    }
    for item in (profile.get("projects") or {}).get("items") or []:
        for tech in item.get("technologies") or []:
            name = tech.get("name")
            if name:
                candidate_names.add(str(name).lower())

    fabricated: list[str] = []
    for name in sorted(_skill_names(tailored)):
        hits = find_skill_hits(name)
        taxonomy_canonical = hits[0].canonical if hits else None
        if taxonomy_canonical is None:
            fabricated.append(f"{name} (not in taxonomy)")
        elif name not in candidate_names:
            fabricated.append(name)

    if fabricated:
        return CheckResult(
            "T4_unsupported_skills",
            "failed",
            f"skills without candidate evidence: {', '.join(fabricated[:8])}",
        )
    return CheckResult(
        "T4_unsupported_skills",
        "passed",
        "all tailored skills exist in candidate evidence and the taxonomy",
    )


def _check_missing_never_inserted(
    tailored: Mapping[str, Any],
    match_result: Mapping[str, Any] | None,
    analysis: Mapping[str, Any] | None,
) -> CheckResult:
    tailored_names = _skill_names(tailored)
    unaddressed = tailored.get("unaddressed_jd_requirements") or []

    leaked = [
        requirement
        for requirement in unaddressed
        if isinstance(requirement, str) and requirement.strip().lower() in tailored_names
    ]
    if leaked:
        return CheckResult(
            "T5_missing_skills_not_inserted",
            "failed",
            f"unaddressed requirements appear as skills: {', '.join(leaked)}",
        )

    if analysis is not None:
        missing_required = match_result.get("missing_required") or [] if match_result else []
        inserted_missing = [
            name
            for name in missing_required
            if isinstance(name, str) and name.strip().lower() in tailored_names
        ]
        if inserted_missing:
            return CheckResult(
                "T5_missing_skills_not_inserted",
                "failed",
                f"missing_required skills inserted: {', '.join(inserted_missing)}",
            )
    return CheckResult(
        "T5_missing_skills_not_inserted",
        "passed",
        "no missing JD requirement was inserted into the resume",
    )


def _months_between(start_iso: str, end_iso: str) -> int | None:
    try:
        sy, sm = int(start_iso[:4]), int(start_iso[5:7])
        ey, em = int(end_iso[:4]), int(end_iso[5:7])
        if not (1 <= sm <= 12 and 1 <= em <= 12):
            return None
    except (ValueError, TypeError):
        return None
    return (ey * 12 + em) - (sy * 12 + sm) + 1


def check_experience_consistency(
    tailored: Mapping[str, Any], profile: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    infos: list[str] = []
    profile_items = (profile.get("experience") or {}).get("items") or []

    for index, item in enumerate(tailored.get("experience") or []):
        source_index = item.get("source_index")
        if not isinstance(source_index, int) or not (0 <= source_index < len(profile_items)):
            failures.append(f"experience[{index}] has invalid source_index")
            continue
        source = profile_items[source_index]

        for field_name in ("title", "company"):
            tailored_value = item.get(field_name)
            source_value = source.get(field_name)
            if tailored_value is not None and tailored_value != source_value:
                failures.append(f"experience[{index}].{field_name} differs from candidate evidence")

        date_range = item.get("date_range_raw")
        expected_range = (
            f"{source.get('start_raw')} - {source.get('end_raw')}"
            if source.get("start_raw") and source.get("end_raw")
            else None
        )
        if date_range is not None and expected_range and date_range != expected_range:
            failures.append(f"experience[{index}] date range altered")

        start_iso = source.get("start_iso")
        end_iso = source.get("end_iso")
        if start_iso and end_iso and end_iso < start_iso:
            infos.append(f"experience[{index}] end precedes start")
        months = source.get("duration_months")
        computed = (
            _months_between(start_iso, end_iso)
            if isinstance(start_iso, str) and isinstance(end_iso, str)
            else None
        )
        if months is not None and computed is not None and months != computed:
            infos.append(f"experience[{index}] duration mismatch vs ISO dates")
    return failures, infos


def check_project_consistency(tailored: Mapping[str, Any], profile: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    profile_projects = (profile.get("projects") or {}).get("items") or []
    for index, item in enumerate(tailored.get("projects") or []):
        source_index = item.get("source_index")
        if not isinstance(source_index, int) or not (0 <= source_index < len(profile_projects)):
            failures.append(f"projects[{index}] has invalid source_index")
            continue
        source = profile_projects[source_index]
        tailored_techs = {str(tech).lower() for tech in item.get("technologies") or []}
        source_techs = {
            str(_val(tech.get("name"))).lower()
            for tech in source.get("technologies") or []
            if tech.get("name")
        }
        extra = tailored_techs - source_techs
        if extra:
            failures.append(
                f"projects[{index}] technologies not in candidate evidence: "
                + ", ".join(sorted(extra))
            )
    return failures


def run_truth_checks(
    tailored_resume: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
    analysis: Mapping[str, Any] | None,
    match_result: Mapping[str, Any] | None,
) -> list[CheckResult]:
    tailored = tailored_resume.get("resume") or {}

    t1 = _check_containment(tailored, candidate_profile)
    t2 = _check_original_fidelity(tailored, candidate_profile)
    t3 = _check_evidence_refs_resolvable(tailored, candidate_profile)
    t4 = _check_no_fabricated_skills(tailored, candidate_profile, analysis)

    t5 = _check_missing_never_inserted(tailored, match_result, analysis)
    consistency_failures, chronology_infos = check_experience_consistency(
        tailored, candidate_profile
    )
    project_failures = check_project_consistency(tailored, candidate_profile)
    if consistency_failures or project_failures:
        t6 = CheckResult(
            "T6_employer_title_date_consistency",
            "failed",
            "; ".join((consistency_failures + project_failures)[:6]),
        )
    else:
        t6 = CheckResult(
            "T6_employer_title_date_consistency",
            "passed",
            "titles, employers, and date ranges match candidate evidence",
        )

    duplicates: list[str] = []
    seen: dict[str, int] = {}
    for _index, item in enumerate(tailored.get("experience") or []):
        for bullet in item.get("highlights") or []:
            key = base_normalize(str(bullet.get("final_text")))
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 2:
                duplicates.append(key[:40])
    if duplicates:
        t8 = CheckResult(
            "T8_duplicate_content",
            "failed",
            f"duplicate bullets detected ({len(duplicates)})",
        )
    else:
        t8 = CheckResult("T8_duplicate_content", "passed", "no duplicate bullets")

    pii_hit_count = 0
    for _field_label, text in _iter_tailored_texts(tailored):
        pii_hit_count += len(_EMAIL_RE.findall(text))
        pii_hit_count += sum(
            1 for m in _PHONE_RE.finditer(text) if 7 <= sum(ch.isdigit() for ch in m.group(0)) <= 15
        )
    if pii_hit_count:
        t9 = CheckResult(
            "T9_pii_absence",
            "failed",
            f"pii-like patterns found in tailored output (count={pii_hit_count})",
        )
    else:
        t9 = CheckResult("T9_pii_absence", "passed", "no PII patterns present")

    meta = tailored.get("metadata") or {}
    rewrite_records = [
        change
        for change in tailored.get("changes") or []
        if isinstance(change, Mapping) and change.get("operation") == "bullet_rewrite_llm"
    ]
    # Absent metadata defaults to deterministic mode (the safe Phase 5 default).
    deterministic_only = bool(meta.get("deterministic_only", True))
    source_profile_id = tailored.get("source_profile_id")
    profile_id = candidate_profile.get("profile_id")
    t10_problems: list[str] = []
    if deterministic_only and rewrite_records:
        t10_problems.append("deterministic_only=True but llm rewrite records exist")
    if source_profile_id and profile_id and source_profile_id != profile_id:
        t10_problems.append("source_profile_id does not match candidate profile id")
    if t10_problems:
        t10 = CheckResult("T10_meta_consistency", "failed", "; ".join(t10_problems))
    else:
        t10 = CheckResult("T10_meta_consistency", "passed", "metadata consistent")

    checks = [t1, t2, t3, t4, t5, t6, t8, t9, t10]

    if chronology_infos:
        checks.append(CheckResult("chronology_info", "info", "; ".join(chronology_infos[:4])))

    return checks


__all__ = ["run_truth_checks"]
