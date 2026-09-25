"""Target Job Description analysis and keyword matching against Candidate evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.jdunderstanding.taxonomy import find_skill_hits
from app.resume_intelligence.models import StructuredResume


@dataclass
class JdComparisonResult:
    target_title: str = "Target Role"
    target_company: str = "Target Employer"
    matched_keywords: list[str] = field(default_factory=list)
    unsupported_keywords: list[str] = field(default_factory=list)
    jd_skills_all: list[str] = field(default_factory=list)
    guidance: str = ""


_DISPLAY_OVERRIDES: dict[str, str] = {
    "sql": "SQL",
    "pl/sql": "PL/SQL",
    "aws": "AWS",
    "gcp": "GCP",
    "html": "HTML",
    "css": "CSS",
    "api": "API",
    "rest": "REST",
    "ci/cd": "CI/CD",
    "cnn": "CNN",
    "rnn": "RNN",
    "nlp": "NLP",
    "ml": "ML",
    "ai": "AI",
    "iot": "IoT",
    "nosql": "NoSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "fastapi": "FastAPI",
    "graphql": "GraphQL",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "snowflake": "Snowflake",
    "python": "Python",
    "git": "Git",
    "linux": "Linux",
    "ebs": "EBS",
}


def format_skill_display(name: str) -> str:
    lower = name.strip().lower()
    if lower in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[lower]
    return name.strip().title()


def compare_jd_and_resume(
    resume: StructuredResume,
    target_job: dict[str, Any] | None = None,
    *,
    target_role: str | None = None,
) -> JdComparisonResult:
    """Extract keywords from JD and classify into supported vs unsupported candidate skills."""
    job = target_job or {}
    title = str(job.get("title") or target_role or "Target Role").strip()
    company = str(job.get("company") or "Target Employer").strip()
    description = str(job.get("description") or "").strip()

    # Collect candidate's verified skills
    candidate_skills_lower = {s.lower() for s in resume.technologies}
    for sk_group in resume.skills:
        for s in sk_group.skills:
            candidate_skills_lower.add(s.lower())
    for proj in resume.projects:
        for t in proj.tech_stack:
            candidate_skills_lower.add(t.lower())
    for exp in resume.experience:
        for t in exp.technologies:
            candidate_skills_lower.add(t.lower())
    if resume.raw_text:
        for hit in find_skill_hits(resume.raw_text):
            candidate_skills_lower.add(hit.canonical.lower())

    # Extract skills from JD text
    jd_text = f"{title} {description}"
    hits = find_skill_hits(jd_text)

    jd_skills: list[str] = []
    matched: list[str] = []
    unsupported: list[str] = []

    seen_canonical: set[str] = set()
    for hit in hits:
        cname = format_skill_display(hit.matched_as or hit.canonical)
        canon_lower = hit.canonical.lower()
        if canon_lower in seen_canonical:
            continue
        seen_canonical.add(canon_lower)
        jd_skills.append(cname)

        if canon_lower in candidate_skills_lower or cname.lower() in candidate_skills_lower:
            matched.append(cname)
        else:
            unsupported.append(cname)

    guidance = ""
    if unsupported:
        guidance = (
            f"Note: {', '.join(unsupported[:5])} are required/preferred in the target JD, "
            "but are NOT evidenced in your resume. Per zero-fabrication policy, they were not added."
        )

    return JdComparisonResult(
        target_title=title,
        target_company=company,
        matched_keywords=sorted(matched),
        unsupported_keywords=sorted(unsupported),
        jd_skills_all=sorted(jd_skills),
        guidance=guidance,
    )
