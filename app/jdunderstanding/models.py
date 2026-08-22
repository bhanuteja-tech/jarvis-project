"""Structured schema for JD understanding outputs.

Every extracted fact is wrapped with evidence (verbatim span + logical field
+ method + confidence). ``ExtractionStatus`` keeps EXPLICIT / INFERRED /
UNKNOWN distinguishable across all fields.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractionStatus(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class RequirementLevel(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNKNOWN = "unknown"


class SectionKind(str, Enum):
    RESPONSIBILITIES = "responsibilities"
    REQUIREMENTS = "requirements"
    QUALIFICATIONS = "qualifications"
    PREFERRED = "preferred"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    BENEFITS = "benefits"
    COMPENSATION = "compensation"
    ABOUT_COMPANY = "about_company"
    ABOUT_ROLE = "about_role"
    OTHER = "other"


class SkillCategory(str, Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    CLOUD = "cloud"
    DATABASE = "database"
    TOOL = "tool"
    CONCEPT = "concept"
    SOFT_SKILL = "soft_skill"
    DOMAIN = "domain"


class Evidence(BaseModel):
    """Verbatim supporting span from the source JD text."""

    text: str
    field: str  # e.g. "job.description", "section:Requirements", "job.salary"
    method: ExtractionMethod = ExtractionMethod.DETERMINISTIC
    confidence: Confidence = Confidence.HIGH
    line: int | None = None


class SkillCategoryValue:
    pass


class SkillRequirement(BaseModel):
    name: str  # canonical taxonomy name
    matched_as: str  # alias actually found in the JD
    category: SkillCategory
    requirement: RequirementLevel = RequirementLevel.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)


class ExperienceRequirement(BaseModel):
    min_years: int | None = None
    max_years: int | None = None
    level_word: str | None = None
    raw: str | None = None
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)


class EducationItem(BaseModel):
    degree: str
    field_of_study: str | None = None
    evidence: Evidence


class ResponsibilityItem(BaseModel):
    text: str
    section: SectionKind = SectionKind.RESPONSIBILITIES
    evidence: Evidence


class QualificationItem(BaseModel):
    text: str
    requirement: RequirementLevel = RequirementLevel.UNKNOWN
    evidence: Evidence


class CertificationItem(BaseModel):
    name: str
    evidence: Evidence


class SalaryParsed(BaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = None
    period: str | None = None


class SalaryField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    canonical_min: float | None = None
    canonical_max: float | None = None
    canonical_currency: str | None = None
    canonical_period: str | None = None
    jd_text_raw: str | None = None
    parsed_from_text: SalaryParsed | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class WorkArrangementInfo(BaseModel):
    mode: Literal["onsite", "remote", "hybrid"] | None = None
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)


class LocationInfo(BaseModel):
    job_location: str | None = None
    remote_eligibility: bool | None = None
    company_location: str | None = None
    status: ExtractionStatus = ExtractionStatus.UNKNOWN


class RoleInfo(BaseModel):
    title_as_posted: str | None = None
    aliases_matched: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None


class SeniorityField(BaseModel):
    level: str | None = None  # explicit seniority word from the JD/title
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    evidence: Evidence | None = None


class EmploymentInfo(BaseModel):
    value: str | None = None
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    evidence: Evidence | None = None


class SkillsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    required: list[SkillRequirement] = Field(default_factory=list)
    preferred: list[SkillRequirement] = Field(default_factory=list)


class ResponsibilitiesField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[ResponsibilityItem] = Field(default_factory=list)


class QualificationsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[QualificationItem] = Field(default_factory=list)


class EducationField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[EducationItem] = Field(default_factory=list)


class CertificationsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[CertificationItem] = Field(default_factory=list)


class KeywordsField(BaseModel):
    status: ExtractionStatus = ExtractionStatus.UNKNOWN
    items: list[dict[str, Any]] = Field(default_factory=list)  # KeywordItem dicts


class CoverageInfo(BaseModel):
    sections_found: list[str] = Field(default_factory=list)
    unrecognized_headings: int = 0


class ExtractionMeta(BaseModel):
    methods_used: list[ExtractionMethod] = Field(
        default_factory=lambda: [ExtractionMethod.DETERMINISTIC]
    )
    llm_used: bool = False
    text_chars: int = 0
    truncated: bool = False
    duration_ms: float | None = None


class JDAnalysis(BaseModel):
    job_index: int
    job_ref: dict[str, Any]
    role: RoleInfo = Field(default_factory=RoleInfo)
    seniority: SeniorityField = Field(default_factory=SeniorityField)
    skills: SkillsField = Field(default_factory=SkillsField)
    responsibilities: ResponsibilitiesField = Field(default_factory=ResponsibilitiesField)
    qualifications: QualificationsField = Field(default_factory=QualificationsField)
    experience: ExperienceRequirement = Field(default_factory=ExperienceRequirement)
    education: EducationField = Field(default_factory=EducationField)
    employment_type: EmploymentInfo = Field(default_factory=EmploymentInfo)
    work_arrangement: WorkArrangementInfo = Field(default_factory=WorkArrangementInfo)
    location: LocationInfo = Field(default_factory=LocationInfo)
    salary: SalaryField = Field(default_factory=SalaryField)
    certifications: CertificationsField = Field(default_factory=CertificationsField)
    domain_terms: list[str] = Field(default_factory=list)
    keywords: KeywordsField = Field(default_factory=KeywordsField)
    coverage: CoverageInfo = Field(default_factory=CoverageInfo)
    extraction_meta: ExtractionMeta = Field(default_factory=ExtractionMeta)
    confidence_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    status: Literal["ANALYZED", "PARTIAL", "FAILED", "SKIPPED"]
    job_index: int
    job_ref: dict[str, Any] = Field(default_factory=dict)
    analysis: JDAnalysis | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "AnalysisResult",
    "CertificationItem",
    "CertificationsField",
    "Confidence",
    "CoverageInfo",
    "EducationField",
    "EducationItem",
    "EmploymentInfo",
    "Evidence",
    "ExperienceRequirement",
    "ExtractionMeta",
    "ExtractionMethod",
    "ExtractionStatus",
    "JDAnalysis",
    "JobRef",
    "KeywordsField",
    "LocationInfo",
    "QualificationItem",
    "QualificationsField",
    "RequirementLevel",
    "ResponsibilitiesField",
    "ResponsibilityItem",
    "RoleInfo",
    "SalaryField",
    "SalaryParsed",
    "SectionKind",
    "SeniorityField",
    "SkillCategory",
    "SkillRequirement",
    "SkillsField",
    "WorkArrangementInfo",
]


class JobRef(BaseModel):
    source: str
    source_job_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "source_job_id": self.source_job_id}
