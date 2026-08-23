"""Candidate / resume schema (Pydantic v2).

Reuses the frozen Phase-2 ``Evidence``/status/confidence enums so downstream
phases see one provenance vocabulary. Every factual field wrapper carries
``status`` (EXPLICIT / INFERRED / UNKNOWN) plus evidence; UNKNOWN is a
first-class state and is never back-filled with guesses.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.jdunderstanding.models import (
    Confidence,
    Evidence,
    ExtractionMethod,
    ExtractionStatus,
)
from app.ranking.preferences import EmploymentType


class SourceFormat(StrEnum):
    PLAIN_TEXT = "plain_text"
    STRUCTURED = "structured"


class ResumeSectionKind(StrEnum):
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    PREFERENCES = "preferences"
    OTHER = "other"


class DegreeLevel(StrEnum):
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"
    DIPLOMA = "diploma"
    BOOTCAMP = "bootcamp"


class IdentityField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    full_name: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class LinkItem(BaseModel):
    label: str | None = None  # e.g. linkedin | github | other
    url: str


class ContactField(BaseModel):
    """PII quarantine block. Values here must never be logged."""

    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    pii: Literal[True] = True
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    links: list[LinkItem] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class SummaryField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    text: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class CandidateSkill(BaseModel):
    name: str  # canonical taxonomy name (frozen jdunderstanding taxonomy)
    matched_as: str
    category: str  # SkillCategory value from the frozen taxonomy
    evidence: list[Evidence] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    start_raw: str | None = None
    end_raw: str | None = None
    start_iso: str | None = None  # YYYY-MM-DD (month/day defaults documented)
    end_iso: str | None = None
    is_current: bool = False
    duration_months: int | None = None
    highlights: list[str] = Field(default_factory=list)
    skills_in_role: list[CandidateSkill] = Field(default_factory=list)
    evidence: Evidence


class ExperienceField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    total_years: float | None = None
    items: list[ExperienceItem] = Field(default_factory=list)


class EducationItem(BaseModel):
    degree: str  # canonical DegreeLevel value or raw lowercase keyword
    degree_raw: str
    field_of_study: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    evidence: Evidence


class EducationField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[EducationItem] = Field(default_factory=list)


class CertificationItem(BaseModel):
    name: str
    evidence: Evidence


class CertificationsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[CertificationItem] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    technologies: list[CandidateSkill] = Field(default_factory=list)
    evidence: Evidence


class ProjectsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[ProjectItem] = Field(default_factory=list)


class SalaryPreference(BaseModel):
    amount: float
    currency: str | None = None
    period: str | None = None


class PreferencesInfo(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    locations: list[str] = Field(default_factory=list)
    remote: bool | None = None
    relocation: bool | None = None
    employment_types: list[str] = Field(default_factory=list)  # EmploymentType values
    salary_min: SalaryPreference | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class SkillsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[CandidateSkill] = Field(default_factory=list)


class CoverageInfo(BaseModel):
    sections_found: list[str] = Field(default_factory=list)
    unrecognized_headings: int = 0


class ProfileMeta(BaseModel):
    source_format: SourceFormat
    text_chars: int = 0
    truncated: bool = False
    duration_ms: float | None = None


class CandidateProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source_format: SourceFormat
    identity: IdentityField = Field(default_factory=IdentityField)
    contact: ContactField = Field(default_factory=ContactField)
    summary: SummaryField = Field(default_factory=SummaryField)
    skills: SkillsField = Field(default_factory=SkillsField)
    experience: ExperienceField = Field(default_factory=ExperienceField)
    education: EducationField = Field(default_factory=EducationField)
    certifications: CertificationsField = Field(default_factory=CertificationsField)
    projects: ProjectsField = Field(default_factory=ProjectsField)
    preferences: PreferencesInfo = Field(default_factory=PreferencesInfo)
    coverage: CoverageInfo = Field(default_factory=CoverageInfo)
    metadata: ProfileMeta
    redacted: bool = False
    warnings: list[str] = Field(default_factory=list)


class CandidateResult(BaseModel):
    status: Literal["PARSED", "PARTIAL", "FAILED", "SKIPPED"]
    profile: CandidateProfile | None = None
    reason: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "CandidateProfile",
    "CandidateResult",
    "CertificationsField",
    "Confidence",
    "ContactField",
    "DegreeLevel",
    "EducationField",
    "EducationItem",
    "EmploymentType",
    "Evidence",
    "ExperienceField",
    "ExperienceItem",
    "ExtractionMethod",
    "ExtractionStatus",
    "IdentityField",
    "LinkItem",
    "PreferencesInfo",
    "ProfileMeta",
    "ProjectsField",
    "ProjectItem",
    "ResumeSectionKind",
    "SalaryPreference",
    "SkillsField",
    "CandidateSkill",
    "SourceFormat",
    "SummaryField",
]
