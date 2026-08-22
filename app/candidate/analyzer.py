"""ResumeAnalyzer orchestrator (Phase 3).

One ``candidate_input`` => one ``CandidateResult``:

- absent input          -> SKIPPED (graph node translates to a no-op)
- empty text            -> FAILED(empty_resume)
- oversized text        -> FAILED(max_chars_violation)  [hard cap, no truncation]
- structured input      -> validated directly against the profile schema
- text input            -> deterministic extraction pipeline
- unexpected exception  -> raised to the graph node, which fails open
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.candidate.extractors import (
    extract_certification_items,
    extract_contact,
    extract_education_items,
    extract_experience_field,
    extract_identity,
    extract_preferences,
    extract_project_items,
    extract_skills_field,
)
from app.candidate.models import (
    CandidateProfile,
    CandidateResult,
    CertificationsField,
    ContactField,
    CoverageInfo,
    EducationField,
    ExperienceItem,
    IdentityField,
    ProfileMeta,
    ProjectsField,
    SourceFormat,
    SummaryField,
)
from app.candidate.text_sections import build_document, segment_resume
from app.config.settings import Settings
from app.jdunderstanding.models import Confidence, Evidence, ExtractionStatus

logger = logging.getLogger(__name__)


class ResumeAnalyzer:
    source_name = "candidate"

    def __init__(self, settings: Settings, *, now: datetime | None = None) -> None:
        self._settings = settings
        self._now = now

    async def build_profile(self, candidate_input: Mapping[str, Any] | None) -> CandidateResult:
        if not isinstance(candidate_input, Mapping) or not candidate_input:
            return CandidateResult(status="SKIPPED", reason="no_input")

        if "structured" in candidate_input:
            return self._from_structured(candidate_input["structured"])
        if "text" in candidate_input:
            return self._from_text(candidate_input["text"])

        return CandidateResult(
            status="FAILED",
            reason="invalid_candidate_input",
            errors=[
                {
                    "source": self.source_name,
                    "kind": "CandidateInputError",
                    "retryable": False,
                    "message": "candidate_input must contain 'text' or 'structured'",
                }
            ],
        )

    # ------------------------------------------------------------------
    # Structured path
    # ------------------------------------------------------------------
    def _from_structured(self, payload: Any) -> CandidateResult:
        started = time.perf_counter()
        if not isinstance(payload, dict):
            return CandidateResult(status="FAILED", reason="invalid_structured_input")
        try:
            data = dict(payload)
            data.setdefault("profile_id", uuid.uuid4().hex)
            data["source_format"] = SourceFormat.STRUCTURED.value
            if "metadata" not in data:
                data["metadata"] = {"source_format": SourceFormat.STRUCTURED.value}
            profile = CandidateProfile.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - typed failure envelope
            logger.warning(
                "structured candidate input invalid",
                extra={"source": self.source_name},
                exc_info=exc,
            )
            return CandidateResult(
                status="FAILED",
                reason="invalid_structured_input",
                errors=[
                    {
                        "source": self.source_name,
                        "kind": type(exc).__name__,
                        "retryable": False,
                        "message": "structured candidate input failed validation",
                    }
                ],
            )
        profile.metadata.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return self._finalize(profile)

    # ------------------------------------------------------------------
    # Text path
    # ------------------------------------------------------------------
    def _from_text(self, raw: Any) -> CandidateResult:
        started = time.perf_counter()
        if not isinstance(raw, str):
            return CandidateResult(status="FAILED", reason="empty_resume")
        text = raw.strip()
        max_chars = self._settings.candidate_max_chars
        if not text:
            return CandidateResult(status="FAILED", reason="empty_resume")
        if len(text) > max_chars:
            return CandidateResult(
                status="FAILED", reason="max_chars_violation"
            )

        document = build_document(text, max_chars=max_chars)
        segmentation = segment_resume(document)

        emails, phones, links, contact_evidence = extract_contact(text)
        name, name_evidence = extract_identity(
            [block.text for block in document.blocks]
        )

        skills_field = extract_skills_field(segmentation, document.plain_text)
        experience_field = extract_experience_field(
            segmentation, now=self._now or datetime.now().astimezone()
        )
        education_items = extract_education_items(segmentation, document.plain_text)
        certification_items = extract_certification_items(text)
        project_items = extract_project_items(segmentation)
        preferences_info = extract_preferences(text)

        summary_section = next(
            (
                section
                for section in segmentation.sections
                if section.kind.value == "summary" and section.text.strip()
            ),
            None,
        )
        summary_field = (
            SummaryField(
                status=ExtractionStatus.EXPLICIT,
                text=summary_section.text[:400],
                evidence=[
                    Evidence(
                        text=summary_section.text[:200],
                        field="resume.summary",
                        confidence=Confidence.HIGH,
                    )
                ],
            )
            if summary_section is not None
            else SummaryField(status=ExtractionStatus.UNKNOWN)
        )

        warnings: list[str] = []
        if segmentation.unrecognized_headings:
            warnings.append(
                f"{segmentation.unrecognized_headings} unrecognized resume heading(s)"
            )
        if experience_field.status is ExtractionStatus.UNKNOWN:
            warnings.append("no experience section detected")

        profile = CandidateProfile(
            source_format=SourceFormat.PLAIN_TEXT,
            identity=(
                IdentityField(
                    status=ExtractionStatus.INFERRED,
                    full_name=name,
                    evidence=[name_evidence],
                )
                if name_evidence is not None
                else IdentityField()
            ),
            contact=ContactField(
                status=(
                    ExtractionStatus.EXPLICIT
                    if (emails or phones or links)
                    else ExtractionStatus.UNKNOWN
                ),
                emails=emails,
                phones=phones,
                links=links,
                evidence=contact_evidence,
            ),
            summary=summary_field,
            skills=skills_field,
            experience=experience_field,
            education=EducationField(
                status=(
                    ExtractionStatus.EXPLICIT if education_items else ExtractionStatus.UNKNOWN
                ),
                items=education_items,
            ),
            certifications=CertificationsField(
                status=(
                    ExtractionStatus.EXPLICIT
                    if certification_items
                    else ExtractionStatus.UNKNOWN
                ),
                items=certification_items,
            ),
            projects=ProjectsField(
                status=(
                    ExtractionStatus.EXPLICIT if project_items else ExtractionStatus.UNKNOWN
                ),
                items=project_items,
            ),
            preferences=preferences_info,
            coverage=CoverageInfo(
                sections_found=sorted({s.kind.value for s in segmentation.sections}),
                unrecognized_headings=segmentation.unrecognized_headings,
            ),
            metadata=ProfileMeta(
                source_format=SourceFormat.PLAIN_TEXT,
                text_chars=len(document.plain_text),
                truncated=document.truncated,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
            warnings=warnings,
        )

        status = "PARSED"
        core_unknown = (
            profile.skills.status is ExtractionStatus.UNKNOWN
            and profile.experience.status is ExtractionStatus.UNKNOWN
        )
        if core_unknown:
            status = "PARTIAL"

        return self._finalize(profile, status=status)

    # ------------------------------------------------------------------
    def _finalize(
        self, profile: CandidateProfile, *, status: str = "PARSED"
    ) -> CandidateResult:
        if self._settings.candidate_redact_pii and not profile.redacted:
            profile = _redact(profile)
        return CandidateResult(status=status, profile=profile)


def _redact(profile: CandidateProfile) -> CandidateProfile:
    """Strip quarantined PII values while preserving the redaction fact."""
    data = profile.model_dump()
    contact = data["contact"]
    contact["emails"] = []
    contact["phones"] = []
    contact["links"] = []
    contact["evidence"] = []
    identity = data["identity"]
    identity["full_name"] = None
    identity["evidence"] = []
    data["redacted"] = True
    return CandidateProfile.model_validate(data)


def build_analyzer(settings: Settings, *, now: datetime | None = None) -> ResumeAnalyzer:
    return ResumeAnalyzer(settings, now=now)


__all__ = ["ResumeAnalyzer", "build_analyzer"]
