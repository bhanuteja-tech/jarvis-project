"""Validation orchestration: truth + ATS -> ValidationReport.

Severity contract:
- any truth check failed  => overall FAIL
- otherwise any warning (or ats mismatch) => WARN
- otherwise PASS

Confidence: high (clean, analysis available) / medium (warnings or
jd_analysis_missing) / low (truth failure or >2 warnings).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.validation.ats import evaluate_ats
from app.validation.models import (
    AtsSection,
    CheckResult,
    TruthSection,
    ValidationReport,
)
from app.validation.truth import run_truth_checks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationOutcome:
    report: ValidationReport


def validate_resume(
    tailored_result: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    match_results: Sequence[Mapping[str, Any]] | None,
    jd_analyses: Sequence[Mapping[str, Any]] | None,
    jobs: Sequence[Mapping[str, Any]] | None,
) -> ValidationOutcome:
    started = time.perf_counter()
    tailored = tailored_result.get("resume")
    if not isinstance(tailored, Mapping):
        tailored = {}

    job_index_value = tailored.get("target_job_index")
    evaluated_job_index = job_index_value if isinstance(job_index_value, int) else None

    analysis = None
    for entry in jd_analyses or []:
        if entry.get("job_index") == evaluated_job_index:
            analysis = entry.get("analysis")
            break

    match_result = None
    for wrapper in match_results or []:
        if wrapper.get("job_index") == evaluated_job_index:
            match_result = wrapper
            break

    profile = candidate_result.get("profile") or {}
    job = None
    if evaluated_job_index is not None and jobs:
        if 0 <= evaluated_job_index < len(jobs):
            job = jobs[evaluated_job_index]

    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    # ---- truth checks -------------------------------------------------------
    truth_checks: list[CheckResult] = []
    try:
        truth_checks.extend(
            run_truth_checks(tailored, profile, analysis, match_result)
        )
    except Exception as exc:  # noqa: BLE001 - one check failing never crashes all
        logger.exception("truth validation crashed")
        truth_checks.append(
            CheckResult("truth_validation", "failed",
                        f"truth validator crashed: {type(exc).__name__}")
        )

    # ---- ats checks -----------------------------------------------------------
    ats_checks: list[CheckResult] = []
    metrics = None
    try:
        ats_checks, metrics = evaluate_ats(
            tailored, profile, analysis, match_result
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ats validation crashed")
        ats_checks.append(
            CheckResult("ats_validation", "failed",
                        f"ats validator crashed: {type(exc).__name__}")
        )

    truth_failed = any(check.status == "failed" for check in truth_checks)
    ats_warned = any(check.status in {"warning", "failed"} for check in ats_checks)

    truth_status = "FAIL" if truth_failed else "PASS"
    ats_status = "WARN" if ats_warned or not ats_checks else "PASS"

    if truth_failed:
        overall = "FAIL"
    elif ats_warned or warnings:
        overall = "WARN"
    else:
        overall = "PASS"

    warning_count = len(warnings)
    if truth_failed:
        confidence = "low"
    elif warning_count > 2 or not analysis:
        confidence = "medium"
    else:
        confidence = "high"

    report = ValidationReport(
        overall_status=overall,
        evaluated_job_index=evaluated_job_index,
        truth=TruthSection(status=truth_status, checks=truth_checks),
        ats=AtsSection(status=ats_status, checks=ats_checks, metrics=metrics),
        confidence=confidence,
        warnings=warnings,
        errors=errors,
    )
    logger.info(
        "validation complete",
        extra={
            "source": "validation",
            "operation": "validate_resume",
            "job_index": evaluated_job_index,
            "overall_status": overall,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return ValidationOutcome(report=report)


def validate_resume_safe(
    tailored_result: Mapping[str, Any] | None,
    candidate_result: Mapping[str, Any] | None,
    match_results: Sequence[Mapping[str, Any]] | None,
    jd_analyses: Sequence[Mapping[str, Any]] | None,
    jobs: Sequence[Mapping[str, Any]] | None,
) -> tuple[bool, ValidationReport | None]:
    """Skip semantics helper used by the graph node.

    Returns (should_run, report). When tailoring produced no usable resume,
    should_run is False and no report is generated.
    """
    if not isinstance(tailored_result, Mapping):
        return False, None
    status = str(tailored_result.get("status") or "").lower()
    if status in {"skipped", "failed"}:
        return False, None
    if not isinstance(tailored_result.get("resume"), Mapping):
        return False, None
    _ = candidate_result, match_results, jd_analyses, jobs
    return True, None


__all__ = ["ValidationOutcome", "validate_resume", "validate_resume_safe"]
