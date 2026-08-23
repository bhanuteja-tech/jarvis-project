"""JDAnalyzer orchestrator: deterministic pipeline + optional semantic merge.

Guarantees:
- a job is never lost: every input yields an AnalysisResult
  (ANALYZED / PARTIAL / FAILED / SKIPPED);
- ``NO_REQUIREMENTS_FOUND`` is a valid ANALYZED outcome — clearly distinct
  from FAILED;
- LLM enhancement is off unless configured AND a client is supplied; its
  claims pass through the evidence validator before merging.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

from app.config.settings import Settings
from app.jdunderstanding.extractors import (
    build_salary_field,
    extract_certifications,
    extract_education,
    extract_experience,
    extract_skills,
)
from app.jdunderstanding.llm import (
    DisabledJdLlmClient,
    JdLlmClient,
    SemanticClaimValidator,
    build_llm_payload,
)
from app.jdunderstanding.models import (
    AnalysisResult,
    Confidence,
    EmploymentInfo,
    Evidence,
    ExtractionMethod,
    ExtractionStatus,
    JDAnalysis,
    QualificationItem,
    QualificationsField,
    RequirementLevel,
    ResponsibilitiesField,
    ResponsibilityItem,
    RoleInfo,
    SectionKind,
    SeniorityField,
    SkillsField,
    WorkArrangementInfo,
)
from app.jdunderstanding.sections import segment_document
from app.jdunderstanding.text import bullet_items, extract_text_document

logger = logging.getLogger(__name__)

_WORK_MODE_WORDS = (
    ("remote", "remote"),
    ("hybrid", "hybrid"),
    ("on-site", "onsite"),
    ("onsite", "onsite"),
    ("work from home", "remote"),
)


def build_analyzer(settings: Settings, *, llm_client: JdLlmClient | None = None) -> JDAnalyzer:
    client = llm_client if settings.jd_llm_enabled else None
    if settings.jd_llm_enabled and client is None:
        client = DisabledJdLlmClient()
        logger.warning("jd_llm_enabled but no client supplied; semantic stage disabled")
    return JDAnalyzer(settings, llm_client=client)


class JDAnalyzer:
    source_name = "jd_analysis"

    def __init__(self, settings: Settings, *, llm_client: JdLlmClient | None = None) -> None:
        self._settings = settings
        self._llm = llm_client  # None => deterministic-only

    async def analyze_ranked(
        self,
        jobs: Sequence[Mapping[str, Any]],
        ranked_jobs: Sequence[Mapping[str, Any]] | None,
        *,
        now: float | None = None,
    ) -> list[AnalysisResult]:
        """Analyze the top-K ranked jobs; remaining jobs become SKIPPED."""
        ranked_list = list(ranked_jobs or [])
        top_k = max(1, int(self._settings.jd_top_k))
        results: list[AnalysisResult] = []

        selected = ranked_list[:top_k]
        for wrapper in selected:
            index_value = wrapper.get("job_index")
            if not isinstance(index_value, int) or not (0 <= index_value < len(jobs)):
                results.append(
                    AnalysisResult(
                        status="SKIPPED",
                        job_index=-1,
                        reason="ranked wrapper missing valid job_index",
                    )
                )
                continue
            results.append(await self.analyze_job(jobs[index_value], index_value))

        analyzed_indices = {r.job_index for r in results}
        for index in range(len(jobs)):
            if index not in analyzed_indices:
                job = jobs[index]
                results.append(
                    AnalysisResult(
                        status="SKIPPED",
                        job_index=index,
                        job_ref={
                            "source": job.get("source"),
                            "source_job_id": job.get("source_job_id"),
                        },
                        reason="outside_top_k",
                    )
                )
        return results

    async def analyze_job(self, job: Mapping[str, Any], job_index: int) -> AnalysisResult:
        started = time.perf_counter()
        warnings: list[str] = []
        job_ref = {"source": job.get("source"), "source_job_id": job.get("source_job_id")}

        description = job.get("description")
        requirements_text = job.get("requirements")
        responsibilities_text = job.get("responsibilities")

        raw_candidates = [
            text
            for text in (
                _plain_from_extra(job),
                description if isinstance(description, str) else None,
                requirements_text if isinstance(requirements_text, str) else None,
                responsibilities_text if isinstance(responsibilities_text, str) else None,
            )
            if text and text.strip()
        ]
        if not raw_candidates:
            return AnalysisResult(
                status="FAILED",
                job_index=job_index,
                job_ref=job_ref,
                reason="empty_description",
            )

        raw_html = "\n".join(raw_candidates)
        document = extract_text_document(raw_html, max_chars=self._settings.jd_max_chars)
        if document.truncated:
            warnings.append(f"jd truncated to {self._settings.jd_max_chars} characters")

        segmentation = segment_document(document)

        skills_required, skills_preferred, keyword_items = extract_skills(
            document.plain_text, segmentation
        )
        experience = extract_experience(document.plain_text, segmentation)
        education_items = extract_education(document.plain_text, segmentation)
        certification_items = extract_certifications(document.plain_text)
        salary_field = build_salary_field(job.get("salary"), document.plain_text)

        role_title = job.get("title") if isinstance(job.get("title"), str) else None

        work_arrangement, arrangement_warnings = _work_arrangement(job, document.plain_text)
        warnings.extend(arrangement_warnings)

        responsibilities_items: list[ResponsibilityItem] = []
        qualifications_items: list[QualificationItem] = []
        for section in segmentation.sections:
            if section.kind is SectionKind.RESPONSIBILITIES:
                for item in bullet_items(section.text):
                    responsibilities_items.append(
                        ResponsibilityItem(
                            text=item,
                            section=SectionKind.RESPONSIBILITIES,
                            evidence=Evidence(
                                text=item[:200],
                                field=f"section:{section.label or 'Responsibilities'}",
                                confidence=Confidence.HIGH,
                            ),
                        )
                    )
        requirements_section = next(
            (
                s
                for s in segmentation.sections
                if s.kind in (SectionKind.REQUIREMENTS, SectionKind.QUALIFICATIONS)
            ),
            None,
        )
        if requirements_section is not None:
            for item in bullet_items(requirements_section.text):
                level = (
                    RequirementLevel.PREFERRED
                    if requirements_section.kind is SectionKind.PREFERRED
                    else RequirementLevel.REQUIRED
                )
                qualifications_items.append(
                    QualificationItem(
                        text=item,
                        requirement=level,
                        evidence=Evidence(
                            text=item[:200],
                            field=(
                                "section:"
                                + (requirements_section.label or requirements_section.kind.value)
                            ),
                            confidence=Confidence.HIGH,
                        ),
                    )
                )

        analysis = JDAnalysis(
            job_index=job_index,
            job_ref=job_ref,
            role=RoleInfo(
                title_as_posted=role_title,
                evidence=Evidence(text=role_title or "", field="job.title"),
            )
            if role_title
            else RoleInfo(),
            seniority=SeniorityField(),
            skills=SkillsField(
                status=(
                    ExtractionStatus.EXPLICIT
                    if skills_required or skills_preferred
                    else ExtractionStatus.UNKNOWN
                ),
                required=skills_required,
                preferred=skills_preferred,
            ),
            responsibilities=ResponsibilitiesField(
                status=(
                    ExtractionStatus.EXPLICIT
                    if responsibilities_items
                    else ExtractionStatus.UNKNOWN
                ),
                items=responsibilities_items,
            ),
            qualifications=QualificationsField(
                status=(
                    ExtractionStatus.EXPLICIT if qualifications_items else ExtractionStatus.UNKNOWN
                ),
                items=qualifications_items,
            ),
            experience=(experience if experience is not None else _unknown_experience()),
            education=_education_field(education_items),
            employment_type=_employment_info(job),
            work_arrangement=work_arrangement,
            location=_location_info(job),
            salary=salary_field,
            certifications=_certification_field(certification_items),
            domain_terms=[item.term for item in keyword_items if item.category.value == "concept"][
                :12
            ],
            keywords=_keywords_field(keyword_items),
            coverage=_coverage(segmentation, document),
            extraction_meta=_meta(document, llm_used=False, started=started),
            confidence_summary=_confidence_summary(skills_required, skills_preferred),
            warnings=list(warnings),
        )

        if self._llm is not None and getattr(self._llm, "enabled", True):
            analysis, semantic_warnings = await self._apply_semantic(analysis, document.plain_text)
            warnings.extend(semantic_warnings)

        status = "PARTIAL" if not (skills_required or responsibilities_items) else "ANALYZED"
        return AnalysisResult(
            status=status,
            job_index=job_index,
            job_ref=job_ref,
            analysis=analysis,
            warnings=warnings,
        )

    async def _apply_semantic(
        self, analysis: JDAnalysis, plain_text: str
    ) -> tuple[JDAnalysis, list[str]]:
        """Evidence-validated semantic merge. Unsupported claims are dropped."""
        assert self._llm is not None
        payload = build_llm_payload(
            analysis.model_dump(mode="json"),
            plain_text,
            max_chars=self._settings.jd_max_chars,
        )
        try:
            claims_wrapper = await self._llm.analyze_structured(
                system_prompt="Extract additional structured facts.",
                payload=payload,
                schema={"type": "object"},
            )
        except Exception as exc:  # noqa: BLE001 - provider failures never fail analysis
            logger.warning("jd semantic stage failed", exc_info=exc)
            analysis.extraction_meta.llm_used = False
            return analysis, [f"semantic stage failed: {type(exc).__name__}"]

        claims = claims_wrapper.get("claims") if isinstance(claims_wrapper, dict) else []
        if not isinstance(claims, list):
            return analysis, ["semantic output malformed; ignored"]

        validator = SemanticClaimValidator(plain_text)
        accepted, rejected = validator.filter_claims(claims)
        warnings: list[str] = []
        if rejected:
            warnings.append(f"unverifiable semantic claims rejected: {', '.join(rejected)}")

        for claim in accepted:
            name = str(claim.get("name") or "").strip().lower()
            if not name:
                continue
            already = any(
                skill.name == name
                for skill in (*analysis.skills.required, *analysis.skills.preferred)
            )
            if not already:
                from app.jdunderstanding.models import SkillCategory, SkillRequirement

                analysis.skills.preferred.append(
                    SkillRequirement(
                        name=name,
                        matched_as=str(claim.get("matched_as") or name),
                        category=SkillCategory.CONCEPT,
                        requirement=RequirementLevel.PREFERRED,
                        evidence=[
                            Evidence(
                                text=str(claim.get("evidence", {}).get("text", "")),
                                field="semantic",
                                method=ExtractionMethod.SEMANTIC,
                                confidence=Confidence.MEDIUM,
                            )
                        ],
                    )
                )
        analysis.extraction_meta.llm_used = bool(accepted) or analysis.extraction_meta.llm_used
        methods = set(analysis.extraction_meta.methods_used)
        if accepted:
            methods.add(ExtractionMethod.SEMANTIC)
        analysis.extraction_meta.methods_used = sorted(methods, key=lambda m: m.value)
        return analysis, warnings


def _plain_from_extra(job: Mapping[str, Any]) -> str | None:
    extra = job.get("extra") or {}
    value = extra.get("description_plain")
    return value if isinstance(value, str) and value.strip() else None


def _unknown_experience():
    from app.jdunderstanding.models import ExperienceRequirement

    return ExperienceRequirement(status=ExtractionStatus.UNKNOWN)


def _education_field(items):
    from app.jdunderstanding.models import EducationField

    return EducationField(
        status=ExtractionStatus.EXPLICIT if items else ExtractionStatus.UNKNOWN,
        items=items,
    )


def _employment_info(job: Mapping[str, Any]) -> EmploymentInfo:
    value = job.get("employment_type")
    if isinstance(value, str) and value.strip():
        return EmploymentInfo(
            value=value.strip(),
            status=ExtractionStatus.EXPLICIT,
            evidence=Evidence(text=value.strip(), field="job.employment_type"),
        )
    return EmploymentInfo(status=ExtractionStatus.UNKNOWN)


def _work_arrangement(
    job: Mapping[str, Any], plain_text: str
) -> tuple[WorkArrangementInfo, list[str]]:
    extra = job.get("extra") or {}
    workplace = extra.get("workplace_type")
    lowered = plain_text.lower()

    mode: str | None = None
    evidence_span: str | None = None
    if isinstance(workplace, str) and workplace.strip().lower() in {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
    }:
        normalized = workplace.strip().lower()
        mode = "onsite" if normalized == "on-site" else normalized
        evidence_span = workplace
    else:
        location_value = job.get("location")
        if isinstance(location_value, str) and location_value.strip().lower() == "remote":
            mode = "remote"
            evidence_span = location_value
        else:
            for word, canonical_mode in _WORK_MODE_WORDS:
                position = lowered.find(word)
                if position >= 0:
                    mode = canonical_mode
                    evidence_span = plain_text[position : position + len(word)]
                    break

    if mode is None or evidence_span is None:
        return WorkArrangementInfo(status=ExtractionStatus.UNKNOWN), []

    return (
        WorkArrangementInfo(
            mode=mode,  # type: ignore[arg-type]
            status=ExtractionStatus.EXPLICIT,
            evidence=[Evidence(text=evidence_span, field="job.description")],
        ),
        [],
    )


def _location_info(job: Mapping[str, Any]):
    from app.jdunderstanding.models import LocationInfo

    location_value = job.get("location")
    if isinstance(location_value, str) and location_value.strip():
        remote = location_value.strip().lower() == "remote"
        return LocationInfo(
            job_location=location_value.strip(),
            remote_eligibility=True if remote else None,
            status=ExtractionStatus.EXPLICIT,
        )
    return LocationInfo(status=ExtractionStatus.UNKNOWN)


def _certification_field(items):
    from app.jdunderstanding.models import CertificationsField

    return CertificationsField(
        status=ExtractionStatus.EXPLICIT if items else ExtractionStatus.UNKNOWN,
        items=items,
    )


def _keywords_field(items):
    from app.jdunderstanding.models import KeywordsField

    return KeywordsField(
        status=ExtractionStatus.EXPLICIT if items else ExtractionStatus.UNKNOWN,
        items=[item.model_dump() for item in items],
    )


def _coverage(segmentation, document):
    from app.jdunderstanding.models import CoverageInfo

    return CoverageInfo(
        sections_found=sorted({section.kind.value for section in segmentation.sections}),
        unrecognized_headings=segmentation.unrecognized_headings,
    )


def _meta(document, *, llm_used: bool, started: float):
    from app.jdunderstanding.models import ExtractionMeta

    return ExtractionMeta(
        methods_used=[ExtractionMethod.DETERMINISTIC],
        llm_used=llm_used,
        text_chars=len(document.plain_text),
        truncated=document.truncated,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _confidence_summary(required, preferred) -> dict[str, Any]:
    high = sum(
        1
        for skill in (*required, *preferred)
        for evidence in skill.evidence
        if evidence.confidence is Confidence.HIGH
    )
    total_skills = len(required) + len(preferred)
    return {
        "skills_total": total_skills,
        "high_confidence_evidence_spans": high,
        "note": "per-fact confidence lives on each Evidence object",
    }


__all__ = ["JDAnalyzer", "build_analyzer"]
