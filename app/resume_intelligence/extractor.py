"""Extractor to build StructuredResume from CandidateProfile, raw text, or editor state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.resume_intelligence.models import (
    EducationEntry,
    ExperienceEntry,
    PersonalInfo,
    ProjectEntry,
    SkillCategoryGroup,
    StructuredResume,
)

_METRIC_RE = re.compile(
    r"(?:\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?[KMBkmb]?|\d+k\+?|\d+\+?\s*(?:users|clients|requests|transactions|writes|events|records|clusters|nodes|pipelines|services|hours|minutes|seconds|ms)|<\s*\d+ms|p(?:90|95|99)\s*(?:latency|response)?|\b\d{1,3}(?:,\d{3})+\b)",
    re.IGNORECASE,
)


def extract_metrics_from_text(text: str) -> list[str]:
    """Find explicit quantifiable metrics (percentages, scale, latency) in candidate text."""
    if not text:
        return []
    matches = _METRIC_RE.findall(text)
    return list(dict.fromkeys(m.strip() for m in matches if m.strip()))


def build_structured_resume(
    source: Any,
    *,
    raw_text: str | None = None,
) -> StructuredResume:
    """Transform candidate profile, session state, editor state, or text into StructuredResume."""
    resume = StructuredResume()
    evidence_corpus: list[str] = []

    if isinstance(source, StructuredResume):
        return source

    data = source if isinstance(source, Mapping) else {}

    # Case 1: Editor / Canvas state format
    if "fullName" in data or "skillGroups" in data:
        name = str(data.get("fullName") or "").strip()
        resume.personal_info = PersonalInfo(
            name=name,
            email=str(data.get("contactEmail") or "").strip(),
            phone=str(data.get("contactPhone") or "").strip(),
            location=str(data.get("contactLocation") or "").strip(),
            linkedin=str(data.get("linkedinUrl") or "").strip(),
            github=str(data.get("githubUrl") or "").strip(),
            portfolio=str(data.get("portfolioUrl") or "").strip(),
        )
        resume.summary = str(data.get("summary") or "").strip()
        if resume.summary:
            evidence_corpus.append(resume.summary)

        # Education
        for edu in data.get("education") or []:
            if isinstance(edu, Mapping):
                entry = EducationEntry(
                    id=str(edu.get("id") or ""),
                    degree=str(edu.get("degree") or "").strip(),
                    institution=str(edu.get("institution") or "").strip(),
                    location=str(edu.get("location") or "").strip(),
                    dates=str(edu.get("dates") or "").strip(),
                    gpa=str(edu.get("gpa") or "").strip(),
                )
                resume.education.append(entry)
                evidence_corpus.extend([entry.degree, entry.institution, entry.location])

        # Projects
        for p in data.get("projects") or []:
            if isinstance(p, Mapping):
                tech_raw = str(p.get("techStack") or p.get("tech_stack_raw") or "").strip()
                tech_list = [t.strip() for t in tech_raw.split(",") if t.strip()]
                bullets = [str(b).strip() for b in (p.get("bullets") or []) if str(b).strip()]
                entry = ProjectEntry(
                    id=str(p.get("id") or ""),
                    title=str(p.get("title") or "").strip(),
                    tech_stack=tech_list,
                    tech_stack_raw=tech_raw,
                    bullets=bullets,
                    links=str(p.get("links") or "").strip(),
                    metrics=extract_metrics_from_text(" ".join(bullets)),
                )
                resume.projects.append(entry)
                evidence_corpus.append(entry.title)
                evidence_corpus.append(tech_raw)
                evidence_corpus.extend(bullets)

        # Skills
        for sk in data.get("skillGroups") or []:
            if isinstance(sk, Mapping):
                skills_raw = str(sk.get("skills") or sk.get("skills_raw") or "").strip()
                skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]
                group = SkillCategoryGroup(
                    id=str(sk.get("id") or ""),
                    category=str(sk.get("category") or "Technical Skills").strip(),
                    skills=skills_list,
                    skills_raw=skills_raw,
                )
                resume.skills.append(group)
                evidence_corpus.append(group.category)
                evidence_corpus.extend(skills_list)

        # Certifications
        for cert in data.get("certifications") or []:
            c_str = str(cert).strip()
            if c_str:
                resume.certifications.append(c_str)
                evidence_corpus.append(c_str)

        # Experience
        for exp in data.get("experience") or []:
            if isinstance(exp, Mapping):
                highlights = [str(h).strip() for h in (exp.get("highlights") or []) if str(h).strip()]
                entry = ExperienceEntry(
                    id=str(exp.get("id") or ""),
                    title=str(exp.get("title") or "").strip(),
                    company=str(exp.get("company") or "").strip(),
                    location=str(exp.get("location") or "").strip(),
                    dates=str(exp.get("dates") or "").strip(),
                    highlights=highlights,
                    is_current="present" in str(exp.get("dates") or "").lower(),
                )
                resume.experience.append(entry)
                evidence_corpus.extend([entry.title, entry.company])
                evidence_corpus.extend(highlights)

    # Case 2: CandidateProfile structure (from Phase 3 backend)
    elif "profile" in data or "identity" in data:
        prof = data.get("profile") if isinstance(data.get("profile"), Mapping) else data

        # Identity & Contact
        identity = prof.get("identity") or {}
        contact = prof.get("contact") or {}
        emails = contact.get("emails") or []
        phones = contact.get("phones") or []
        links = contact.get("links") or []

        linkedin_url = ""
        github_url = ""
        for link in links:
            url = link.get("url") if isinstance(link, Mapping) else str(link)
            if "linkedin" in url.lower():
                linkedin_url = url
            elif "github" in url.lower():
                github_url = url

        resume.personal_info = PersonalInfo(
            name=str(identity.get("full_name") or contact.get("name") or "").strip(),
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            linkedin=linkedin_url,
            github=github_url,
        )

        # Summary
        summary_field = prof.get("summary") or {}
        resume.summary = str(summary_field.get("text") or "").strip()
        if resume.summary:
            evidence_corpus.append(resume.summary)

        # Education
        edu_field = prof.get("education") or {}
        for item in edu_field.get("items") or []:
            if isinstance(item, Mapping):
                degree = str(item.get("degree_raw") or item.get("degree") or "").strip()
                inst = str(item.get("institution") or "").strip()
                dates = str(item.get("graduation_year") or "").strip()
                entry = EducationEntry(
                    degree=degree,
                    institution=inst,
                    dates=dates,
                )
                resume.education.append(entry)
                evidence_corpus.extend([degree, inst])

        # Experience
        exp_field = prof.get("experience") or {}
        for item in exp_field.get("items") or []:
            if isinstance(item, Mapping):
                highlights = [str(h).strip() for h in (item.get("highlights") or []) if str(h).strip()]
                entry = ExperienceEntry(
                    title=str(item.get("title") or "").strip(),
                    company=str(item.get("company") or "").strip(),
                    location=str(item.get("location") or "").strip(),
                    dates=str(item.get("start_raw") or "") + (" - " + str(item.get("end_raw")) if item.get("end_raw") else ""),
                    highlights=highlights,
                    is_current=bool(item.get("is_current")),
                )
                resume.experience.append(entry)
                evidence_corpus.extend([entry.title, entry.company])
                evidence_corpus.extend(highlights)

        # Projects
        proj_field = prof.get("projects") or {}
        for item in proj_field.get("items") or []:
            if isinstance(item, Mapping):
                bullets = []
                desc = item.get("description")
                if desc:
                    bullets.append(str(desc).strip())
                techs = [
                    t.get("name") if isinstance(t, Mapping) else str(t)
                    for t in (item.get("technologies") or [])
                ]
                entry = ProjectEntry(
                    title=str(item.get("name") or "").strip(),
                    tech_stack=techs,
                    tech_stack_raw=", ".join(techs),
                    bullets=bullets,
                    links=str(item.get("url") or "").strip(),
                    metrics=extract_metrics_from_text(" ".join(bullets)),
                )
                resume.projects.append(entry)
                evidence_corpus.append(entry.title)
                evidence_corpus.extend(techs)
                evidence_corpus.extend(bullets)

        # Skills
        skills_field = prof.get("skills") or {}
        cat_map: dict[str, list[str]] = {}
        for item in skills_field.get("items") or []:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                cat = str(item.get("category") or "Technical Skills").strip()
                if name:
                    cat_map.setdefault(cat, []).append(name)
        for cat, slist in cat_map.items():
            group = SkillCategoryGroup(
                category=cat,
                skills=slist,
                skills_raw=", ".join(slist),
            )
            resume.skills.append(group)
            evidence_corpus.append(cat)
            evidence_corpus.extend(slist)

        # Certifications
        certs_field = prof.get("certifications") or {}
        for item in certs_field.get("items") or []:
            name = item.get("name") if isinstance(item, Mapping) else str(item)
            if name:
                resume.certifications.append(str(name).strip())
                evidence_corpus.append(str(name).strip())

    # Raw text inclusion
    raw_src = raw_text or data.get("raw_text") or (source if isinstance(source, str) else "")
    if isinstance(raw_src, str) and raw_src.strip():
        resume.raw_text = raw_src.strip()
        evidence_corpus.append(resume.raw_text)

    # Extract all technologies and metrics across the entire resume
    full_corpus_text = " ".join(evidence_corpus)
    resume.metrics_extracted = extract_metrics_from_text(full_corpus_text)

    # Populate technologies from taxonomy
    from app.jdunderstanding.taxonomy import find_skill_hits

    hits = find_skill_hits(full_corpus_text)
    tech_set: set[str] = set()
    for hit in hits:
        tech_set.add(hit.canonical)
    resume.technologies = sorted(tech_set)

    resume.evidence_corpus = evidence_corpus
    return resume
