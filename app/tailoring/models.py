"""Tailored resume schema.

Every tailored fact traces back to CandidateProfile paths via
``evidence_refs``. ``TailoredBullet`` keeps both the original and final text
so diffs can prove nothing was fabricated. PII (identity/contact) is never
copied into this artifact.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TailoringStatus(StrEnum):
    TAILORED = "tailored"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChangeRecord(BaseModel):
    operation: str  # skill_priority | highlight_select | project_rank |
    # summary_generate | dedupe_bullet | section_omit |
    # bullet_rewrite_llm
    section: str
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)


class EvidenceRefMixin(BaseModel):
    evidence_refs: list[str] = Field(default_factory=list)


class TailoredSkill(EvidenceRefMixin):
    name: str  # canonical taxonomy name
    display: str  # canonical name or candidate's matched_as spelling
    requirement: Literal["required", "preferred", "additional"]


class TailoredBullet(BaseModel):
    index: int  # original highlight index within the source experience item
    original_text: str
    final_text: str
    evidence_ref: str


class TailoredExperienceItem(BaseModel):
    source_index: int
    title: str | None = None
    company: str | None = None
    date_range_raw: str | None = None
    highlights: list[TailoredBullet] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TailoredProject(BaseModel):
    source_index: int
    name: str | None = None
    description: str | None = None
    url: str | None = None
    technologies: list[str] = Field(default_factory=list)  # canonical names
    evidence_ref: str


class TailoredEducationItem(BaseModel):
    degree: str
    field_of_study: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    evidence_ref: str


class TailoredCertification(BaseModel):
    name: str
    evidence_ref: str


class TailoredSummary(BaseModel):
    text: str
    method: Literal["deterministic_template"] = "deterministic_template"
    evidence_refs: list[str] = Field(default_factory=list)


class TargetJobInfo(BaseModel):
    job_index: int
    job_ref: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    company: str | None = None


class TailoringMeta(BaseModel):
    deterministic_only: bool = True
    duration_ms: float | None = None


class TailoredResume(BaseModel):
    target_job_index: int
    target_job_ref: dict[str, Any] = Field(default_factory=dict)
    target_job_title: str | None = None
    source_profile_id: str

    summary: TailoredSummary
    skills: list[TailoredSkill] = Field(default_factory=list)
    experience: list[TailoredExperienceItem] = Field(default_factory=list)
    projects: list[TailoredProject] = Field(default_factory=list)
    education: list[TailoredEducationItem] = Field(default_factory=list)
    certifications: list[TailoredCertification] = Field(default_factory=list)

    changes: list[ChangeRecord] = Field(default_factory=list)
    unaddressed_jd_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: TailoringMeta = Field(default_factory=TailoringMeta)


class TailoringResult(BaseModel):
    status: TailoringStatus
    resume: TailoredResume | None = None
    reason: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "ChangeRecord",
    "TailoredBullet",
    "TailoredCertification",
    "TailoredEducationItem",
    "TailoredExperienceItem",
    "TailoredProject",
    "TailoredResume",
    "TailoredSkill",
    "TailoredSummary",
    "TailoringResult",
    "TailoringStatus",
    "TargetJobInfo",
]
