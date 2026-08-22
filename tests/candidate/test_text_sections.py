"""Resume section segmentation: heading variants and retention rules."""

from __future__ import annotations

import pytest

from app.candidate.models import ResumeSectionKind
from app.candidate.text_sections import (
    build_document,
    classify_resume_heading,
    segment_resume,
)


def _segment(raw: str, max_chars: int = 30_000):
    return segment_resume(build_document(raw, max_chars=max_chars))


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Professional Experience", ResumeSectionKind.EXPERIENCE),
        ("Work History", ResumeSectionKind.EXPERIENCE),
        ("Employment", ResumeSectionKind.EXPERIENCE),
        ("Education", ResumeSectionKind.EDUCATION),
        ("Technical Skills", ResumeSectionKind.SKILLS),
        ("Projects", ResumeSectionKind.PROJECTS),
        ("Certificates", ResumeSectionKind.CERTIFICATIONS),
        ("Objective", ResumeSectionKind.SUMMARY),
        ("Preferences", ResumeSectionKind.PREFERENCES),
    ],
)
def test_heading_variants_map_correctly(heading: str, expected: ResumeSectionKind) -> None:
    assert classify_resume_heading(heading) is expected


def test_case_and_punctuation_insensitive() -> None:
    assert classify_resume_heading("WORK EXPERIENCE:") is ResumeSectionKind.EXPERIENCE
    assert classify_resume_heading("Technical Skills") is ResumeSectionKind.SKILLS


def test_unknown_heading_retained_as_other() -> None:
    raw = "Volunteer Work\nAnimal shelter volunteering.\n"
    segmentation = _segment(raw)

    assert segmentation.unrecognized_headings == 1
    joined = "\n".join(section.text for section in segmentation.sections)
    assert "Animal shelter" in joined  # never dropped


def test_html_script_content_dropped() -> None:
    raw = "<script>pixel()</script><h2>Skills</h2><p>Python</p>"
    document = build_document(raw, max_chars=10_000)

    assert "pixel" not in document.plain_text.lower()
    assert "Python" in document.plain_text


def test_sections_found_listing() -> None:
    raw = (
        "Summary\nPlatform engineer.\n"
        "Skills\nGo, Kubernetes\n"
        "Professional Experience\nSenior Engineer at Acme\nJan 2020 - Present\n"
        "Shipped things.\n"
        "Education\nBSc in Computer Science, 2015\n"
    )
    segmentation = _segment(raw)
    found = [section.kind.value for section in segmentation.sections if section.blocks or section.kind is not ResumeSectionKind.OTHER]

    assert {"summary", "skills", "experience", "education"} <= set(found)
