"""Tailoring orchestration facade used by the LangGraph node."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.config.settings import Settings
from app.tailoring.generator import gather_evidence_corpus, generate_tailored_resume
from app.tailoring.models import (
    ChangeRecord,
    TailoredResume,
    TailoringResult,
    TailoringStatus,
)
from app.tailoring.validator import (
    DisabledTailoringLlmClient,
    TruthinessValidator,
    rewrite_selected_bullet,
)
from app.tailoring.views import build_profile_view, resolve_target

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TailoringOutcome:
    result: TailoringResult


def tailor_resume(
    candidate_result: Mapping[str, Any] | None,
    match_results: Sequence[Mapping[str, Any]] | None,
    jd_analyses: Sequence[Mapping[str, Any]] | None,
    jobs: Sequence[Mapping[str, Any]] | None,
    tailoring_prefs: Mapping[str, Any] | None,
    settings: Settings,
    *,
    llm_client: Any | None = None,
) -> TailoringOutcome:
    started = time.perf_counter()
    profile_view = build_profile_view(candidate_result)
    if not profile_view.usable:
        return TailoringOutcome(
            result=TailoringResult(status=TailoringStatus.SKIPPED,
                                   reason="no_usable_candidate_profile")
        )

    override_index = None
    if isinstance(tailoring_prefs, Mapping):
        override_value = tailoring_prefs.get("target_job_index")
        if override_value is not None and str(override_value).lstrip("-").isdigit():
            override_index = int(override_value)

    resolution = resolve_target(match_results or [], jd_analyses or [], jobs or [], override_index)
    if resolution.error_reason is not None:
        return TailoringOutcome(
            result=TailoringResult(status=TailoringStatus.FAILED,
                                   reason=resolution.error_reason)
        )
    assert resolution.target is not None  # error_reason None implies target
    target = resolution.target

    matched_skills: frozenset[str] = frozenset()
    for wrapper in match_results or []:
        if wrapper.get("job_index") == target.job_index:
            names = wrapper.get("matched_skills") or []
            matched_skills = frozenset(str(name).strip().lower() for name in names)
            break

    total_years = None
    experience_section = (candidate_result.get("profile") or {}).get("experience") or {}
    raw_years = experience_section.get("total_years")
    if isinstance(raw_years, (int, float)) and not isinstance(raw_years, bool):
        total_years = float(raw_years)

    llm = llm_client if settings.tailoring_llm_enabled else None

    draft, warnings = generate_tailored_resume(
        profile_view,
        target,
        matched_skills=matched_skills,
        total_years=total_years,
        max_highlights=settings.tailor_max_highlights,
        max_projects=settings.tailor_max_projects,
        deterministic_only=(llm is None),
    )

    llm_used = False
    if llm is not None:
        validator = TruthinessValidator(gather_evidence_corpus(profile_view))
        for item in draft.experience:
            for bullet in item.highlights:
                accepted, final_text, warning = await rewrite_selected_bullet(
                    llm,
                    validator,
                    original_text=bullet.final_text,
                    jd_context=target.responsibilities_text
                    or (target.title or ""),
                )
                llm_used = True
                if accepted and final_text != bullet.final_text:
                    changes_note = ChangeRecord(
                        operation="bullet_rewrite_llm",
                        section=f"experience[{item.source_index}]",
                        reason="rewritten by enabled LLM; passed truth guard",
                        evidence_refs=[bullet.evidence_ref],
                    )
                    draft.changes.append(changes_note)
                    bullet.final_text = final_text
                if warning:
                    warnings.append(warning)

    status = TailoringStatus.TAILORED
    if resolution.analysis_missing or not draft.skills or not any(
        item.highlights for item in draft.experience
    ):
        status = TailoringStatus.PARTIAL

    draft.metadata.deterministic_only = not llm_used
    draft.metadata.duration_ms = round((time.perf_counter() - started) * 1000, 2)

    logger.info(
        "tailoring complete",
        extra={
            "source": "tailoring",
            "operation": "tailor_resume",
            "target_job_index": target.job_index,
            "status": status.value,
            "changes": len(draft.changes),
        },
    )
    return TailoringOutcome(
        result=TailoringResult(status=status, resume=draft)
    )


def build_service(settings: Settings, *, llm_client: Any | None = None):
    """Wiring helper returning a ready async callable."""

    async def _service(candidate_result, match_results, jd_analyses, jobs,
                       tailoring_prefs=None) -> TailoringOutcome:
        return await tailor_resume(
            candidate_result,
            match_results,
            jd_analyses,
            jobs,
            tailoring_prefs,
            settings,
            llm_client=llm_client,
        )

    return _service


__all__ = ["TailoringOutcome", "build_service", "tailor_resume"]
