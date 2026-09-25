"""Pydantic models for structured resume representation, rewriting, and validation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PersonalInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class EducationEntry(BaseModel):
    id: str | None = None
    degree: str = ""
    institution: str = ""
    location: str = ""
    dates: str = ""
    gpa: str = ""


class ExperienceEntry(BaseModel):
    id: str | None = None
    title: str = ""
    company: str = ""
    location: str = ""
    dates: str = ""
    highlights: list[str] = Field(default_factory=list)
    is_current: bool = False


class ProjectEntry(BaseModel):
    id: str | None = None
    title: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    tech_stack_raw: str = ""
    bullets: list[str] = Field(default_factory=list)
    links: str = ""
    metrics: list[str] = Field(default_factory=list)


class SkillCategoryGroup(BaseModel):
    id: str | None = None
    category: str = ""
    skills: list[str] = Field(default_factory=list)
    skills_raw: str = ""


class StructuredResume(BaseModel):
    """Normalized, structured internal representation of a complete candidate resume."""

    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    skills: list[SkillCategoryGroup] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    metrics_extracted: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    raw_text: str = ""
    evidence_corpus: list[str] = Field(default_factory=list)

    def get_evidence_tokens(self) -> set[str]:
        """Collect all alphanumeric tokens from the candidate's verified content."""
        from app.dedup.normalize import informative_tokens

        tokens: set[str] = set()
        for text in self.evidence_corpus:
            if isinstance(text, str) and text.strip():
                tokens.update(informative_tokens(text))
        if self.raw_text:
            tokens.update(informative_tokens(self.raw_text))
        if self.summary:
            tokens.update(informative_tokens(self.summary))
        for p in self.projects:
            tokens.update(informative_tokens(p.title))
            for b in p.bullets:
                tokens.update(informative_tokens(b))
            for t in p.tech_stack:
                tokens.update(informative_tokens(t))
        for e in self.experience:
            if e.title:
                tokens.update(informative_tokens(e.title))
            if e.company:
                tokens.update(informative_tokens(e.company))
            for b in e.bullets:
                tokens.update(informative_tokens(b))
            for t in e.technologies:
                tokens.update(informative_tokens(t))
        for s in self.skills:
            for sk in s.skills:
                tokens.update(informative_tokens(sk))
        for c in self.certifications:
            tokens.update(informative_tokens(c))
        return tokens


class FactCheckResult(BaseModel):
    supported: bool = True
    flagged_claims: list[str] = Field(default_factory=list)
    verified_tokens: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FormattingMetadata(BaseModel):
    bullet_style: str = "disc"
    spacing_after: str = "standard"
    line_spacing: str = "standard"


class AiWriteRequest(BaseModel):
    session_id: str | None = None
    section: Literal[
        "summary", "projects", "experience", "skills", "education", "certifications", "header"
    ]
    current_content: Any = None
    user_command: str = ""
    action_type: str = "custom"
    target_role: str | None = None
    target_job: dict[str, Any] | None = None
    bullet_count: int | None = None
    one_page_mode: bool = False
    resume_context: dict[str, Any] | None = None
    raw_resume_text: str | None = None


class AiWriteResponse(BaseModel):
    operation: str = "rewrite_section"
    section: str
    content: dict[str, Any]
    formatting: FormattingMetadata = Field(default_factory=FormattingMetadata)
    ats_keywords_used: list[str] = Field(default_factory=list)
    unsupported_keywords: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    fact_check: FactCheckResult = Field(default_factory=FactCheckResult)
    text_output: str = ""
