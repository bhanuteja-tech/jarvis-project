"""TailoredResume assembly (deterministic).

Consumes validated views + rules and emits a complete ``TailoredResume``
with ChangeRecords for every tailoring decision. A token-subset truth guard
runs over the generated summary as defense-in-depth (all content is built
from profile tokens, so violations indicate bugs, never silent fabrications).
"""

from __future__ import annotations

from collections import Counter

from app.candidate.models import CandidateProfile  # noqa: F401 (typing parity)
from app.tailoring import rules
from app.tailoring.models import (
    ChangeRecord,
    TailoredBullet,
    TailoredCertification,
    TailoredEducationItem,
    TailoredExperienceItem,
    TailoredProject,
    TailoredResume,
    TailoredSkill,
    TailoredSummary,
    TailoringMeta,
)
from app.tailoring.validator import TruthinessValidator
from app.tailoring.views import ExpRef, ProfileView, TargetView


def _skill_path(name: str) -> str:
    return f"resume.skills.items[name={name}]"


def gather_evidence_corpus(profile_view: ProfileView) -> list[str]:
    """All candidate-authored text spans — the factuality universe."""
    texts: list[str] = []
    if profile_view.summary_text:
        texts.append(profile_view.summary_text)
    for skill in profile_view.skills:
        texts.extend((skill.name, skill.display))
    for item in profile_view.experience:
        for value in (item.title, item.company, item.date_range):
            if value:
                texts.append(value)
        texts.extend(item.highlights)
    for project in profile_view.projects:
        for value in (project.name, project.description, project.url):
            if value:
                texts.append(value)
    for education_item in profile_view.education_items:
        texts.extend(
            str(value)
            for value in education_item.values()
            if isinstance(value, str)
        )
    texts.extend(profile_view.certification_names)
    return texts


def generate_tailored_resume(
    profile_view: ProfileView,
    target: TargetView,
    *,
    matched_skills: frozenset[str],
    total_years: float | None,
    max_highlights: int,
    max_projects: int,
    deterministic_only: bool = True,
) -> tuple[TailoredResume, list[str]]:
    warnings: list[str] = []
    changes: list[ChangeRecord] = []
    validator = TruthinessValidator(gather_evidence_corpus(profile_view))

    # ---- skills ------------------------------------------------------------
    tagged = rules.tag_and_rank_skills(
        profile_view.skills, target.required_skills, target.preferred_skills
    )
    tailored_skills: list[TailoredSkill] = [
        TailoredSkill(
            name=skill.name,
            display=skill.name,  # canonical terminology alignment (ATS-safe)
            requirement=requirement,  # type: ignore[arg-type]
            evidence_refs=[_skill_path(skill.name)],
        )
        for skill, requirement in tagged
    ]
    if profile_view.skills:
        changes.append(
            ChangeRecord(
                operation="skill_priority",
                section="skills",
                reason=(
                    "ordered skills with JD-required matches first; canonical "
                    "taxonomy naming applied"
                ),
                evidence_refs=[
                    _skill_path(skill.name) for skill, _tag in tagged[:6]
                ],
            )
        )

    # ---- experience ----------------------------------------------------------
    responsibility_tokens = frozenset(rules.content_tokens(target.responsibilities_text))
    experience_order = rules.order_experience_items(
        profile_view.experience, matched_skills, responsibility_tokens
    )
    seen_bullets: set[str] = set()
    tailored_experience: list[TailoredExperienceItem] = []

    for source_index in experience_order:
        item: ExpRef = next(
            ref for ref in profile_view.experience if ref.index == source_index
        )
        selected_indices, selection_changes = rules.select_highlights(
            item.highlights,
            item.skill_names,
            matched_skills,
            responsibility_tokens,
            max_highlights,
        )
        changes.extend(selection_changes)

        bullets: list[TailoredBullet] = []
        seen_in_item: set[str] = set()
        for highlight_index in sorted(selected_indices):
            original = item.highlights[highlight_index]
            normalized = base_normalize(original)
            if normalized in seen_bullets:
                changes.append(
                    ChangeRecord(
                        operation="dedupe_bullet",
                        section=f"experience[{source_index}]",
                        reason="duplicate identical bullet removed",
                        evidence_refs=[],
                    )
                )
                continue
            seen_bullets.add(normalized)

            final_text = original  # verbatim in deterministic mode
            evidence_ref = (
                f"resume.experience[{source_index}].highlights[{highlight_index}]"
            )
            bullets.append(
                TailoredBullet(
                    index=highlight_index,
                    original_text=original,
                    final_text=final_text,
                    evidence_ref=evidence_ref,
                )
            )

        date_range = item.date_range
        tailored_experience.append(
            TailoredExperienceItem(
                source_index=source_index,
                title=item.title,
                company=item.company,
                date_range_raw=date_range,
                highlights=bullets,
                evidence_refs=[
                    f"resume.experience[{source_index}]"
                ],
            )
        )

    # ---- projects --------------------------------------------------------------
    project_indices, project_change = rules.rank_projects(
        profile_view.projects, matched_skills, max_projects
    )
    if project_change is not None:
        changes.append(project_change)
    tailored_projects: list[TailoredProject] = []
    for source_index in project_indices:
        project: ProjRef = next(
            ref for ref in profile_view.projects if ref.index == source_index
        )
        tailored_projects.append(
            TailoredProject(
                source_index=source_index,
                name=project.name,
                description=project.description,
                url=project.url,
                technologies=list(project.tech_names),
                evidence_ref=f"resume.projects[{source_index}]",
            )
        )

    # ---- education / certifications (verbatim passthrough) ---------------------
    tailored_education = [
        TailoredEducationItem(
            degree=str(item.get("degree")),
            field_of_study=item.get("field_of_study"),
            institution=item.get("institution"),
            graduation_year=item.get("graduation_year"),
            evidence_ref=f"resume.education.items[{index}]",
        )
        for index, item in enumerate(profile_view.education_items)
    ]
    tailored_certifications = [
        TailoredCertification(
            name=name,
            evidence_ref=f"resume.certifications.items[name={name}]",
        )
        for name in profile_view.certification_names
    ]

    # ---- summary ---------------------------------------------------------------
    latest_title = None
    if profile_view.experience:
        latest_title = profile_view.experience[0].title  # resumes are newest-first

    # total_years is the Phase-3-authoritative value (>=80% coverage rule)
    # supplied by the caller; never recomputed here.
    total_years_value = total_years

    top_matched = [name for name in sorted(matched_skills)][:3]
    summary_text, summary_refs = rules.build_summary(
        latest_title, total_years_value, top_matched
    )
    if not validator.is_supported(summary_text):  # defense-in-depth
        warnings.append("generated summary failed truth guard; omitted")
        summary_text = ""
        summary_refs = []
    changes.append(
        ChangeRecord(
            operation="summary_generate",
            section="summary",
            reason="deterministic template over verified candidate facts",
            evidence_refs=summary_refs,
        )
    )

    # ---- unaddressed requirements -----------------------------------------------
    candidate_skill_names = {skill.name for skill in profile_view.skills}
    unaddressed = rules.unaddressed_requirements(
        target.required_skills, candidate_skill_names
    )
    if unaddressed:
        warnings.append(
            "JD requires skills absent from candidate evidence: "
            + ", ".join(unaddressed)
        )

    return (
        TailoredResume(
            target_job_index=target.job_index,
            target_job_ref=target.job_ref,
            target_job_title=target.title,
            source_profile_id=profile_view.profile_id or "",
            summary=TailoredSummary(text=summary_text, evidence_refs=summary_refs),
            skills=tailored_skills,
            experience=tailored_experience,
            projects=tailored_projects,
            education=tailored_education,
            certifications=tailored_certifications,
            changes=changes,
            unaddressed_jd_requirements=unaddressed,
            warnings=warnings,
            metadata=TailoringMeta(deterministic_only=deterministic_only),
        ),
        warnings,
    )


__all__ = ["generate_tailored_resume"]
