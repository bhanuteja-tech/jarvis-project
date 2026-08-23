"""Resume-specific section segmentation.

Reuses the frozen Phase-2 text utilities (stdlib HTML stripping, block
model, bullet splitting) and applies a resume-oriented heading lexicon:

    Professional Experience / Work Experience / Work History / Employment
    Education · Skills / Technical Skills · Projects · Certifications
    Summary / Profile / Objective · Preferences

Unknown headings are retained as OTHER sections — resume content is never
dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.candidate.models import ResumeSectionKind
from app.jdunderstanding.text import TextBlock, TextDocument, extract_text_document

_HEADING_LEXICON: dict[str, ResumeSectionKind] = {
    # experience
    "professional experience": ResumeSectionKind.EXPERIENCE,
    "work experience": ResumeSectionKind.EXPERIENCE,
    "work history": ResumeSectionKind.EXPERIENCE,
    "employment": ResumeSectionKind.EXPERIENCE,
    "employment history": ResumeSectionKind.EXPERIENCE,
    "experience": ResumeSectionKind.EXPERIENCE,
    # education
    "education": ResumeSectionKind.EDUCATION,
    "academic background": ResumeSectionKind.EDUCATION,
    "academics": ResumeSectionKind.EDUCATION,
    "education and training": ResumeSectionKind.EDUCATION,
    # skills
    "skills": ResumeSectionKind.SKILLS,
    "technical skills": ResumeSectionKind.SKILLS,
    "core skills": ResumeSectionKind.SKILLS,
    "key skills": ResumeSectionKind.SKILLS,
    "skillset": ResumeSectionKind.SKILLS,
    "technologies": ResumeSectionKind.SKILLS,
    # projects
    "projects": ResumeSectionKind.PROJECTS,
    "personal projects": ResumeSectionKind.PROJECTS,
    "selected projects": ResumeSectionKind.PROJECTS,
    # certifications
    "certifications": ResumeSectionKind.CERTIFICATIONS,
    "certificates": ResumeSectionKind.CERTIFICATIONS,
    "licenses and certifications": ResumeSectionKind.CERTIFICATIONS,
    "licenses": ResumeSectionKind.CERTIFICATIONS,
    # summary
    "summary": ResumeSectionKind.SUMMARY,
    "professional summary": ResumeSectionKind.SUMMARY,
    "career summary": ResumeSectionKind.SUMMARY,
    "profile": ResumeSectionKind.SUMMARY,
    "objective": ResumeSectionKind.SUMMARY,
    "about me": ResumeSectionKind.SUMMARY,
    # preferences
    "preferences": ResumeSectionKind.PREFERENCES,
    "job preferences": ResumeSectionKind.PREFERENCES,
    "what im looking for": ResumeSectionKind.PREFERENCES,
}

_PREFIX_RULES: tuple[tuple[str, ResumeSectionKind], ...] = (
    ("professional ", ResumeSectionKind.EXPERIENCE),
    ("work ", ResumeSectionKind.EXPERIENCE),
    ("technical ", ResumeSectionKind.SKILLS),
    ("selected ", ResumeSectionKind.PROJECTS),
)

# Conservative cues for plain-text headings that name a REAL section but are
# absent from the canonical lexicon (e.g. "Volunteer Work"). Without a cue
# the line stays body text — project names must never become sections.
_UNRESOLVED_HEADING_CUES: frozenset[str] = frozenset(
    {
        "volunteer",
        "volunteering",
        "activities",
        "interests",
        "hobbies",
        "awards",
        "achievements",
        "honors",
        "publications",
        "references",
        "portfolio",
        "affiliations",
        "languages",
        "background",
    }
)

_TRAILING_PUNCT = re.compile(r"[:：\s]+$")


def normalize_heading(text: str) -> str:
    normalized = text.lower().replace("’", "").replace("'", "")
    normalized = re.sub(r"[^a-z0-9&/ ]+", " ", normalized)
    normalized = _TRAILING_PUNCT.sub("", normalized)
    return " ".join(normalized.split())


def classify_resume_heading(block_text: str) -> ResumeSectionKind | None:
    key = normalize_heading(block_text)
    if key in _HEADING_LEXICON:
        return _HEADING_LEXICON[key]
    for prefix, kind in _PREFIX_RULES:
        if key.startswith(prefix):
            return kind
    return None


def _looks_like_heading_para(block: TextBlock) -> bool:
    text = block.text.strip()
    return (
        block.kind == "para"
        and 0 < len(text) <= 60
        and not text.endswith((".", ";", ","))
        and "\n" not in text
    )


@dataclass
class ResumeSection:
    kind: ResumeSectionKind
    label: str
    blocks: list[TextBlock] = field(default_factory=list)
    line_start: int = 0

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)


@dataclass
class ResumeSegmentation:
    sections: list[ResumeSection]
    unrecognized_headings: int


def segment_resume(document: TextDocument) -> ResumeSegmentation:
    sections: list[ResumeSection] = [
        ResumeSection(kind=ResumeSectionKind.OTHER, label="", line_start=0)
    ]
    unrecognized = 0
    line_cursor = 0

    for block in document.blocks:
        is_heading = False
        kind: ResumeSectionKind | None = None
        label = ""

        if block.kind == "heading":
            is_heading = True
            kind = classify_resume_heading(block.text)
            label = block.text.strip()
        elif _looks_like_heading_para(block):
            kind = classify_resume_heading(block.text)
            if kind is not None:
                is_heading = True
                label = block.text.strip()
            else:
                # Plain-text heading naming an unsupported section: retain it
                # as OTHER rather than silently demoting it to body prose.
                tokens = set(normalize_heading(block.text).split())
                if tokens & _UNRESOLVED_HEADING_CUES:
                    is_heading = True
                    kind = ResumeSectionKind.OTHER
                    label = block.text.strip()
                    unrecognized += 1

        if is_heading:
            if kind is None:
                kind = ResumeSectionKind.OTHER
                unrecognized += 1
            sections.append(ResumeSection(kind=kind, label=label, line_start=line_cursor))
            continue

        sections[-1].blocks.append(block)
        line_cursor += 1

    body = [s for s in sections if s.blocks or s.kind is not ResumeSectionKind.OTHER]
    return ResumeSegmentation(sections=body or sections, unrecognized_headings=unrecognized)


def build_document(text: str, *, max_chars: int) -> TextDocument:
    """Acquire a resume document through the frozen stdlib parser."""
    return extract_text_document(text, max_chars=max_chars)


def section_of(
    segmentation: ResumeSegmentation | None, kind: ResumeSectionKind
) -> ResumeSection | None:
    if segmentation is None:
        return None
    for section in segmentation.sections:
        if section.kind is kind:
            return section
    return None


__all__ = [
    "ResumeSection",
    "ResumeSegmentation",
    "build_document",
    "classify_resume_heading",
    "normalize_heading",
    "segment_resume",
    "section_of",
]
