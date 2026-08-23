"""Deterministic field extractors.

Every function returns schema models carrying verbatim evidence. Nothing is
inferred: absent signals yield UNKNOWN statuses, and salary text is only
structured when an unambiguous currency-anchored pattern matches.
"""

from __future__ import annotations

import re
from typing import Any

from app.jdunderstanding.models import (
    CertificationItem,
    Confidence,
    EducationItem,
    Evidence,
    ExperienceRequirement,
    ExtractionStatus,
    KeywordItem,
    RequirementLevel,
    SalaryField,
    SalaryParsed,
    SectionKind,
    SkillCategory,
    SkillRequirement,
)
from app.jdunderstanding.sections import Segmentation
from app.jdunderstanding.taxonomy import find_skill_hits

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

_REQUIRED_CUES = ("required", "must have", "must-have", "minimum", "strong ")
_PREFERRED_CUES = ("plus", "nice to have", "preferred", "bonus", "desirable")


def _requirement_for_section(kind: SectionKind) -> RequirementLevel:
    if kind in (SectionKind.REQUIREMENTS, SectionKind.SKILLS):
        return RequirementLevel.REQUIRED
    if kind == SectionKind.PREFERRED:
        return RequirementLevel.PREFERRED
    return RequirementLevel.UNKNOWN


def _cue_level(sentence: str) -> RequirementLevel | None:
    lowered = sentence.lower()
    # Required cues take precedence over preferred cues when both appear.
    if any(cue in lowered for cue in _REQUIRED_CUES):
        return RequirementLevel.REQUIRED
    if any(cue in lowered for cue in _PREFERRED_CUES):
        return RequirementLevel.PREFERRED
    return None


def extract_skills(
    document_text: str,
    segmentation: Segmentation,
) -> tuple[list[SkillRequirement], list[SkillRequirement], list[KeywordItem]]:
    """Return (required, preferred, keyword_items)."""
    required_by_name: dict[str, SkillRequirement] = {}
    preferred_by_name: dict[str, SkillRequirement] = {}
    keywords: dict[str, KeywordItem] = {}

    def add_hit(
        canonical: str,
        matched_as: str,
        category: SkillCategory,
        level: RequirementLevel,
        confidence: Confidence,
        span: str,
        field_name: str,
        line: int | None,
    ) -> None:
        # REQUIRED wins precedence; UNKNOWN requirements are recorded under
        # preferred with explicit level=unknown so they stay visible without
        # inflating required-skill matching later.
        bucket = required_by_name if level is RequirementLevel.REQUIRED else preferred_by_name
        existing = bucket.get(canonical)
        evidence = Evidence(
            text=span.strip(),
            field=field_name,
            confidence=confidence,
            line=line,
        )
        if existing is None:
            bucket[canonical] = SkillRequirement(
                name=canonical,
                matched_as=matched_as,
                category=category,
                requirement=level,
                evidence=[evidence],
            )
        else:
            existing.evidence.append(evidence)
            if existing.requirement is RequirementLevel.UNKNOWN:
                existing.requirement = level
        keyword_key = f"{canonical}:{category.value}"
        if keyword_key not in keywords:
            keywords[keyword_key] = KeywordItem(
                term=canonical, category=category, evidence=evidence
            )

    for section in segmentation.sections:
        section_text = section.text
        if not section_text.strip():
            continue
        base_level = _requirement_for_section(section.kind)
        confidence = (
            Confidence.HIGH if base_level is not RequirementLevel.UNKNOWN else Confidence.MEDIUM
        )
        hits = find_skill_hits(section_text)
        for hit in hits:
            span = section_text[max(0, hit.start - 40) : hit.end + 40]
            line = section.line_start + section_text.count("\n", 0, hit.start) + 1
            level = base_level
            if level is RequirementLevel.UNKNOWN:
                cue = _cue_level(span)
                level = cue if cue is not None else RequirementLevel.UNKNOWN
            add_hit(
                hit.canonical,
                hit.matched_as,
                hit.category,
                level,
                confidence,
                span,
                f"section:{section.label or section.kind.value}",
                line,
            )

    # Un-sectioned fallback over the whole text (catches skills outside all
    # recognized sections); lower confidence.
    known_names = {name for name in (*required_by_name.keys(), *preferred_by_name.keys())}
    for hit in find_skill_hits(document_text):
        if hit.canonical in known_names:
            continue
        span = document_text[max(0, hit.start - 40) : hit.end + 40]
        cue = _cue_level(span)
        level = cue if cue is not None else RequirementLevel.UNKNOWN
        add_hit(
            hit.canonical,
            hit.matched_as,
            hit.category,
            level,
            Confidence.LOW,
            span,
            "job.description",
            None,
        )

    required_sorted = sorted(required_by_name.values(), key=lambda s: s.name)
    preferred_sorted = sorted(preferred_by_name.values(), key=lambda s: s.name)
    keyword_items = sorted(keywords.values(), key=lambda k: (k.category.value, k.term))
    return required_sorted, preferred_sorted, keyword_items


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

_RANGE_RE = re.compile(
    r"(?P<min>\d{1,2})\s*(?:to|[-–—])\s*(?P<max>\d{1,2})\s*\+?\s*years?",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(r"(?P<n>\d{1,2})\s*\+?\s*years?", re.IGNORECASE)
_LEVEL_WORDS = (
    "senior-level",
    "entry-level",
    "junior-level",
    "fresh graduate",
    "internship",
    "mid-level",
)

_EDUCATION_RE = re.compile(
    r"\b(?P<deg>bachelor(?:'s)?|master(?:'s)?|phd|doctorate|associate)(?:\s+degree)?"
    r"(?:[^.\n]{0,60}?\bin\s+(?P<field>[A-Z][A-Za-z &/]{2,40}))?",
    re.IGNORECASE,
)

_BARE_DEGREE_RE = re.compile(
    r"\b(?P<degree>bachelor(?:'s)?\s+degree|master(?:'s)?\s+degree|"
    r"bachelor(?:'s)?|master(?:'s)?|phd|doctorate|associate)\b",
    re.IGNORECASE,
)

_CERT_PATTERNS = (
    r"aws certified [a-z ]{3,40}",
    r"azure certified[a-z ]{0,30}",
    r"google cloud certified[a-z ]{0,30}",
    r"certified kubernetes[a-z ]{0,20}",
    r"project management professional",
    r"cissp",
    r"certified scrum master",
)


def extract_experience(
    document_text: str,
    segmentation: Segmentation,
) -> ExperienceRequirement | None:
    experience_sections = [
        section.text
        for section in segmentation.sections
        if section.kind
        in (SectionKind.EXPERIENCE, SectionKind.REQUIREMENTS, SectionKind.QUALIFICATIONS)
    ]
    search_order = [*experience_sections, document_text]

    for candidate_text in search_order:
        match = _RANGE_RE.search(candidate_text)
        if match is not None:
            return ExperienceRequirement(
                min_years=int(match.group("min")),
                max_years=int(match.group("max")),
                raw=match.group(0),
                status=ExtractionStatus.EXPLICIT,
                evidence=[Evidence(text=match.group(0), field="section:experience")],
            )
    for candidate_text in search_order:
        match = _SINGLE_RE.search(candidate_text)
        if match is not None:
            years = int(match.group("n"))
            return ExperienceRequirement(
                min_years=years,
                raw=match.group(0),
                status=ExtractionStatus.EXPLICIT,
                evidence=[Evidence(text=match.group(0), field="section:experience")],
            )

    lowered = document_text.lower()
    for word in _LEVEL_WORDS:
        if word in lowered:
            return ExperienceRequirement(
                level_word=word,
                status=ExtractionStatus.EXPLICIT,
                evidence=[Evidence(text=word, field="job.description")],
            )
    return None  # caller maps to UNKNOWN


def extract_education(
    document_text: str,
    segmentation: Segmentation,
) -> list[EducationItem]:
    items: list[EducationItem] = []
    education_sections = [
        section.text
        for section in segmentation.sections
        if section.kind
        in (SectionKind.EDUCATION, SectionKind.REQUIREMENTS, SectionKind.QUALIFICATIONS)
    ]
    search_texts = [*education_sections, document_text]
    seen_fields: set[str] = set()

    for candidate_text in search_texts:
        for match in _EDUCATION_RE.finditer(candidate_text):
            degree = match.group("deg").lower()
            field_of_study = (
                match.group("field").strip().rstrip(" .,;")
                if match.group("field") else None
            )
            key = f"{degree}:{(field_of_study or '').lower()}"
            if key in seen_fields:
                continue
            seen_fields.add(key)
            items.append(
                EducationItem(
                    degree=degree,
                    field_of_study=field_of_study,
                    evidence=Evidence(text=match.group(0).strip(), field="section:education"),
                )
            )
        if items:
            break

    if not items:
        for candidate_text in search_texts:
            for match in _BARE_DEGREE_RE.finditer(candidate_text):
                degree = match.group("degree").lower()
                key = f"{degree}:"
                if key in seen_fields:
                    continue
                seen_fields.add(key)
                items.append(
                    EducationItem(
                        degree=degree,
                        field_of_study=None,
                        evidence=Evidence(text=match.group(0), field="job.description"),
                    )
                )
            if items:
                break
    return items


def extract_certifications(document_text: str) -> list[CertificationItem]:
    items: list[CertificationItem] = []
    seen: set[str] = set()
    lowered = document_text.lower()
    for pattern in _CERT_PATTERNS:
        match = re.search(pattern, lowered)
        if match is not None:
            name = match.group(0).strip()
            if name not in seen:
                seen.add(name)
                items.append(
                    CertificationItem(
                        name=name.title(),
                        evidence=Evidence(text=name, field="job.description"),
                    )
                )
    return items


# ---------------------------------------------------------------------------
# Salary evidence
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(
    r"(?P<cur>[$€£₹])\s?(?P<a>\d{1,3}(?:[,.]\d{3})*|\d+(?:\.\d+)?)\s?k?"
    r"(?:\s?[-–—to]+\s?(?P<cur2>[$€£₹])?\s?(?P<b>\d{1,3}(?:[,.]\d{3})*|\d+(?:\.\d+)?)\s?k?)?",
    re.IGNORECASE,
)
_PERIOD_HINTS = (
    ("year", "year"),
    ("annum", "year"),
    ("hr", "hour"),
    ("hour", "hour"),
    ("month", "month"),
)


def _money_value(raw_number: str) -> float | None:
    cleaned = raw_number.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value < 1000:
        value *= 1000.0  # "120k" style shorthand handled by caller suffix too
    return value


def parse_salary_span(match: re.Match[str]) -> SalaryParsed:
    currency_symbol = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
    currency = currency_symbol.get(match.group("cur"))
    low_raw, high_raw = match.group("a"), match.group("b")

    def convert(raw: str | None) -> float | None:
        if raw is None:
            return None
        return _money_value(raw)

    minimum = convert(low_raw)
    maximum = convert(high_raw) if high_raw else None
    if maximum is not None and minimum is not None and maximum < minimum:
        minimum, maximum = maximum, minimum

    matched_text = match.group(0).lower()
    period = None
    for hint, canonical_period in _PERIOD_HINTS:
        if hint in matched_text:
            period = canonical_period
            break
    if period is None:
        tail_window = match.string[match.end():match.end() + 30].lower()
        for hint, canonical_period in _PERIOD_HINTS:
            if hint in tail_window:
                period = canonical_period
                break
    return SalaryParsed(min=minimum, max=maximum, currency=currency, period=period)


_UNAMBIGUOUS_SALARY_RE = re.compile(
    _MONEY_RE.pattern + r"(\s*(?:per|/)\s*(?:year|annum|hour|month))?", re.IGNORECASE
)


def build_salary_field(canonical_salary: Any, document_text: str) -> SalaryField:
    """Canonical structured salary passes through untouched; JD text yields
    parsed values ONLY when the unambiguous currency-anchored pattern hits."""
    field_model = SalaryField()

    if isinstance(canonical_salary, dict):
        min_amount = canonical_salary.get("min_amount")
        max_amount = canonical_salary.get("max_amount")
        currency = canonical_salary.get("currency")
        period = canonical_salary.get("period")
        if min_amount is not None or max_amount is not None:
            field_model.status = ExtractionStatus.EXPLICIT
            field_model.canonical_min = float(min_amount) if min_amount is not None else None
            field_model.canonical_max = float(max_amount) if max_amount is not None else None
            field_model.canonical_currency = (
                str(currency).upper() if isinstance(currency, str) else None
            )
            field_model.canonical_period = period if isinstance(period, str) else None

    match = _UNAMBIGUOUS_SALARY_RE.search(document_text)
    if match is not None:
        parsed = parse_salary_span(match)
        jd_evidence = Evidence(
            text=match.group(0), field="job.description", confidence=Confidence.MEDIUM
        )
        field_model.jd_text_raw = match.group(0)
        field_model.parsed_from_text = parsed
        field_model.evidence.append(jd_evidence)
        if field_model.status is ExtractionStatus.UNKNOWN and parsed.min is not None:
            field_model.status = ExtractionStatus.EXPLICIT

    return field_model


__all__ = [
    "extract_certifications",
    "extract_education",
    "extract_experience",
    "extract_skills",
    "build_salary_field",
]
