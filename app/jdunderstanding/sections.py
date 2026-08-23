"""Section segmentation over a block-structured JD document.

JDs are wildly inconsistent ("Responsibilities", "WHAT YOU'LL DO", "Your
impact", "Must have", "Bonus points", ...). Detection therefore uses:

1. an exact-match lexicon of normalized heading variants, then
2. conservative prefix rules (required/preferred/nice/bonus/what/about...).

Unrecognized headings become ``OTHER`` sections — content is never dropped.
Short paragraph lines that look like headings (no ending punctuation,
<= 80 chars) are also considered heading candidates so plain-text and
bold-pseudo-headings work without HTML structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dedup.normalize import base_normalize
from app.jdunderstanding.models import SectionKind
from app.jdunderstanding.text import TextBlock, TextDocument

_HEADING_LEXICON: dict[str, SectionKind] = {
    "responsibilities": SectionKind.RESPONSIBILITIES,
    "what you ll do": SectionKind.RESPONSIBILITIES,
    "what you will do": SectionKind.RESPONSIBILITIES,
    "what youll do": SectionKind.RESPONSIBILITIES,
    "your impact": SectionKind.RESPONSIBILITIES,
    "what youll be doing": SectionKind.RESPONSIBILITIES,
    "the role": SectionKind.ABOUT_ROLE,
    "about the role": SectionKind.ABOUT_ROLE,
    "about this role": SectionKind.ABOUT_ROLE,
    "job summary": SectionKind.ABOUT_ROLE,
    "overview": SectionKind.ABOUT_ROLE,
    "about us": SectionKind.ABOUT_COMPANY,
    "about the company": SectionKind.ABOUT_COMPANY,
    "about the team": SectionKind.ABOUT_COMPANY,
    "who we are": SectionKind.ABOUT_COMPANY,
    "requirements": SectionKind.REQUIREMENTS,
    "requirements essential": SectionKind.REQUIREMENTS,
    "required qualifications": SectionKind.REQUIREMENTS,
    "minimum qualifications": SectionKind.REQUIREMENTS,
    "basic qualifications": SectionKind.REQUIREMENTS,
    "must have": SectionKind.REQUIREMENTS,
    "what we re looking for": SectionKind.REQUIREMENTS,
    "what were looking for": SectionKind.REQUIREMENTS,
    "what youre good at": SectionKind.REQUIREMENTS,
    "qualifications": SectionKind.QUALIFICATIONS,
    "your qualifications": SectionKind.QUALIFICATIONS,
    "skills": SectionKind.SKILLS,
    "skills and experience": SectionKind.SKILLS,
    "nice to have": SectionKind.PREFERRED,
    "preferred qualifications": SectionKind.PREFERRED,
    "bonus points": SectionKind.PREFERRED,
    "bonus qualifications": SectionKind.PREFERRED,
    "good to have": SectionKind.PREFERRED,
    "education": SectionKind.EDUCATION,
    "experience": SectionKind.EXPERIENCE,
    "benefits": SectionKind.BENEFITS,
    "perks": SectionKind.BENEFITS,
    "perks and benefits": SectionKind.BENEFITS,
    "compensation": SectionKind.COMPENSATION,
    "salary": SectionKind.COMPENSATION,
    "compensation and benefits": SectionKind.COMPENSATION,
}

_PREFIX_RULES: tuple[tuple[str, SectionKind], ...] = (
    ("required ", SectionKind.REQUIREMENTS),
    ("minimum ", SectionKind.REQUIREMENTS),
    ("must ", SectionKind.REQUIREMENTS),
    ("preferred ", SectionKind.PREFERRED),
    ("bonus ", SectionKind.PREFERRED),
    ("nice ", SectionKind.PREFERRED),
    ("what you", SectionKind.RESPONSIBILITIES),
    ("about ", SectionKind.ABOUT_COMPANY),
)

_TRAILING_PUNCT = re.compile(r"[:：\s]+$")


def normalize_heading(text: str) -> str:
    normalized = base_normalize(text)
    normalized = normalized.replace("’", "").replace("'", "")
    normalized = _TRAILING_PUNCT.sub("", normalized)
    return normalized.strip()


def _classify_heading(block_text: str) -> SectionKind | None:
    key = normalize_heading(block_text)
    if key in _HEADING_LEXICON:
        return _HEADING_LEXICON[key]
    for prefix, kind in _PREFIX_RULES:
        if key.startswith(prefix):
            return kind
    return None


def _looks_like_heading_para(block: TextBlock) -> bool:
    """Plain-text pseudo-headings: short, no terminal period, not bullets."""
    text = block.text.strip()
    if text.startswith(("-", "•", "*", "·", "–")):
        return False
    return (
        block.kind == "para"
        and 0 < len(text) <= 80
        and not text.endswith((".", ";", ","))
        and "\n" not in text
    )


@dataclass
class Section:
    kind: SectionKind
    label: str
    blocks: list[TextBlock] = field(default_factory=list)
    line_start: int = 0

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)


@dataclass
class Segmentation:
    sections: list[Section]
    unrecognized_headings: int


def segment_document(document: TextDocument) -> Segmentation:
    sections: list[Section] = [Section(kind=SectionKind.OTHER, label="", line_start=0)]
    unrecognized = 0
    line_cursor = 0

    for block in document.blocks:
        is_heading = False
        kind: SectionKind | None = None
        label = ""

        if block.kind == "heading":
            is_heading = True
            kind = _classify_heading(block.text)
            label = block.text.strip()
        elif _looks_like_heading_para(block):
            is_heading = True
            kind = _classify_heading(block.text)
            label = block.text.strip()

        if is_heading:
            if kind is None:
                kind = SectionKind.OTHER
                unrecognized += 1
            section = Section(kind=kind, label=label, line_start=line_cursor)
            sections.append(section)
            continue

        sections[-1].blocks.append(block)
        line_cursor += 1

    return Segmentation(sections=sections[1:] or sections, unrecognized_headings=unrecognized)


def find_sections(segmentation: Segmentation, *kinds: SectionKind) -> list[Section]:
    wanted = set(kinds)
    return [section for section in segmentation.sections if section.kind in wanted]


def full_text_of(document: TextDocument, segmentation: Segmentation) -> str:
    return document.plain_text


__all__ = ["Section", "Segmentation", "find_sections", "full_text_of", "segment_document"]
