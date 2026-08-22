"""Deterministic candidate extractors.

Contact/PII is quarantined; dates are parsed ONLY from explicit forms and
durations computed only when both ends resolve (``Present`` uses the
injected clock). Preferences come exclusively from explicit statements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.candidate.models import (
    CandidateSkill,
    CertificationItem,
    DegreeLevel,
    EducationItem,
    ExperienceField,
    ExperienceItem,
    LinkItem,
    PreferencesInfo,
    ProjectItem,
    SalaryPreference,
    SkillsField,
)
from app.jdunderstanding.models import Confidence, Evidence, ExtractionStatus
from app.jdunderstanding.taxonomy import SkillHit, find_skill_hits
from app.ranking.preferences import EmploymentType, normalize_employment

# ---------------------------------------------------------------------------
# Contact / PII (quarantined)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?")
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)


def _link_label(url: str) -> str:
    lowered = url.lower()
    if "linkedin" in lowered:
        return "linkedin"
    if "github" in lowered:
        return "github"
    return "other"


def extract_contact(text: str) -> tuple[list[str], list[str], list[Any], list[Evidence]]:
    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))[:5]
    phones: list[str] = []
    for match in _PHONE_RE.finditer(text):
        raw = match.group(0).strip()
        digit_count = sum(ch.isdigit() for ch in raw)
        if 7 <= digit_count <= 15 and not _EMAIL_RE.search(raw):
            phones.append(raw)
            if len(phones) >= 3:
                break
    links: list[Any] = []
    for url in list(dict.fromkeys(m.group(0).rstrip(".,;") for m in _URL_RE.finditer(text)))[:6]:
        links.append(LinkItem(label=_link_label(url), url=url))
    evidence = [
        Evidence(text="contact details extracted", field="resume.contact",
                 confidence=Confidence.HIGH)
    ] if (emails or phones or links) else []
    return emails, phones, links, evidence


_NAME_STOPWORDS = re.compile(
    r"(@|https?://|\+\d|curriculum|r[eé]sum[eé]|profile|\b\d{4}\b)", re.IGNORECASE
)


def extract_identity(document_lines: list[str]) -> tuple[str | None, Evidence | None]:
    """Approved heuristic: first clean top line is the candidate name."""
    for line in document_lines[:8]:
        candidate = line.strip().strip("|•-–— ")
        if not candidate or len(candidate) > 50:
            continue
        if _NAME_STOPWORDS.search(candidate):
            continue
        words = candidate.split()
        if not (1 <= len(words) <= 5):
            continue
        if sum(ch.isalpha() for ch in candidate) < len(candidate) * 0.6:
            continue
        evidence = Evidence(
            text=candidate, field="resume.header", confidence=Confidence.MEDIUM
        )
        return candidate, evidence
    return None, None


# ---------------------------------------------------------------------------
# Dates / durations
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "sept": 9,
}
_DATE_TOKEN = r"(?:[A-Za-z]{3,9}\.?,?\s*\d{4}|\d{1,2}/\d{4}|\d{4})"
_DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:–|—|-|to)\s*(?P<end>{_DATE_TOKEN}|present|current|now)",
    re.IGNORECASE,
)
_PRESENT_TOKENS = {"present", "current", "now"}


def parse_date_token(token: str) -> tuple[str | None, bool]:
    """Return (iso_date|None, is_current). Month/day default to 01."""
    cleaned = token.strip().lower().rstrip(".")
    if cleaned in _PRESENT_TOKENS:
        return None, True
    compact = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
    parts = compact.split()
    year = None
    month = 1
    for part in parts:
        if part.isdigit() and len(part) == 4:
            year = int(part)
        elif part[:3] in _MONTHS:
            month = _MONTHS[part[:3]]
    if year is None or not (1900 <= year <= 2100):
        return None, False
    return f"{year:04d}-{month:02d}-01", False


def duration_months(start_iso: str, end_iso: str) -> int:
    sy, sm = int(start_iso[:4]), int(start_iso[5:7])
    ey, em = int(end_iso[:4]), int(end_iso[5:7])
    return max(0, (ey * 12 + em) - (sy * 12 + sm) + 1)


@dataclass
class _RawEntry:
    header_line: str
    date_span_text: str
    start_token: str
    end_token: str
    body_lines: list[str]


def _split_experience_entries(section_text: str) -> list[_RawEntry]:
    lines = section_text.split("\n")
    entries: list[_RawEntry] = []
    current: _RawEntry | None = None
    pending_header: list[str] = []

    def close_pending_into(entry: _RawEntry) -> _RawEntry:
        # Header lines collected before the date line become title/company.
        if pending_header:
            entry.header_line = pending_header[-1]
            entry.body_lines = [*pending_header[:-1][::-1], *entry.body_lines]
            pending_header.clear()
        return entry

    for line in lines:
        stripped = line.strip()
        match = _DATE_RANGE_RE.search(stripped)
        if match is None:
            if current is None:
                pending_header.append(stripped) if stripped else None
            else:
                current.body_lines.append(stripped)
            continue
        if current is not None:
            entries.append(current)
        current = close_pending_into(
            _RawEntry(
                header_line="",
                date_span_text=match.group(0),
                start_token=match.group("start"),
                end_token=match.group("end"),
                body_lines=[],
            )
        )
        trailing = stripped[match.end():].strip(" \t–—-|")
        if trailing:
            current.body_lines.append(trailing)
    if current is not None:
        entries.append(current)
    elif pending_header:
        pass
    return entries


def _title_company(header_line: str) -> tuple[str | None, str | None]:
    text = header_line.strip().strip("|").strip()
    if not text:
        return None, None
    for separator in (" – ", " — ", " - ", " | ", " at "):
        if separator in text:
            left, right = [part.strip() for part in text.split(separator, 1)]
            if left and right:
                return left, right
    return text, None


def extract_experience_field(
    segmentation,
    *,
    now: datetime | None = None,
) -> ExperienceField:
    from app.candidate.text_sections import ResumeSectionKind, section_of

    section = section_of(segmentation, ResumeSectionKind.EXPERIENCE)
    items: list[ExperienceItem] = []
    if section is not None:
        reference = now or datetime.now().astimezone()
        for raw_entry in _split_experience_entries(section.text):
            header = raw_entry.header_line or (
                raw_entry.body_lines[0] if raw_entry.body_lines else ""
            )
            title, company = _title_company(header)
            body = [line for line in raw_entry.body_lines if line != header]
            location: str | None = None
            highlights: list[str] = []
            for line in body:
                if line.lower().startswith(("remote", "hybrid", "onsite", "on-site")) and len(line) < 40:
                    location = line
                    continue
                cleaned = line.lstrip("-•*·–— ").strip()
                if cleaned:
                    highlights.append(cleaned)

            entry_text = "\n".join([header, raw_entry.date_span_text, *body])
            skills_in_role = _skills_from_text(entry_text)

            start_iso, start_current = parse_date_token(raw_entry.start_token)
            end_iso_token, end_is_present = parse_date_token(raw_entry.end_token)
            end_iso = end_iso_token
            is_current = end_is_present or start_current
            if end_iso is None and is_current:
                end_iso = reference.date().isoformat()

            duration: int | None = None
            if start_iso is not None and end_iso is not None:
                duration = duration_months(start_iso, end_iso)

            items.append(
                ExperienceItem(
                    title=title,
                    company=company,
                    location=location,
                    start_raw=raw_entry.start_token,
                    end_raw=raw_entry.end_token,
                    start_iso=start_iso,
                    end_iso=end_iso,
                    is_current=is_current,
                    duration_months=duration,
                    highlights=highlights[:12],
                    skills_in_role=skills_in_role,
                    evidence=Evidence(
                        text=raw_entry.date_span_text,
                        field="resume.experience",
                        confidence=Confidence.HIGH,
                    ),
                )
            )

    durations = [item.duration_months for item in items if item.duration_months is not None]
    total_years: float | None = None
    if items and len(durations) / len(items) >= 0.8:
        total_years = round(sum(durations) / 12.0, 1)

    status = ExtractionStatus.EXPLICIT if items else ExtractionStatus.UNKNOWN
    return ExperienceField(status=status, total_years=total_years, items=items)


# ---------------------------------------------------------------------------
# Skills (frozen taxonomy reuse)
# ---------------------------------------------------------------------------


def _skills_from_text(text: str) -> list[CandidateSkill]:
    skills: dict[str, CandidateSkill] = {}
    for hit in find_skill_hits(text):
        span = text[max(0, hit.start - 30): hit.end + 30].strip()
        key = hit.canonical
        if key in skills:
            skills[key].evidence.append(
                Evidence(text=span, field="resume.skills", confidence=Confidence.MEDIUM)
            )
            continue
        skills[key] = CandidateSkill(
            name=hit.canonical,
            matched_as=hit.matched_as,
            category=hit.category.value,
            evidence=[
                Evidence(text=span, field="resume.skills", confidence=Confidence.MEDIUM)
            ],
        )
    return list(skills.values())


def extract_skills_field(segmentation, full_text: str):
    from app.candidate.text_sections import ResumeSectionKind, section_of

    section = section_of(segmentation, ResumeSectionKind.SKILLS)
    scope = section.text if section is not None else full_text
    items = _skills_from_text(scope)
    if not items and section is not None:
        items = _skills_from_text(full_text)
    return SkillsField(
        status=ExtractionStatus.EXPLICIT if items else ExtractionStatus.UNKNOWN,
        items=items,
    )


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

_DEGREE_MAP: dict[str, DegreeLevel] = {
    "phd": DegreeLevel.PHD,
    "doctorate": DegreeLevel.PHD,
    "mphil": DegreeLevel.PHD,
    "master": DegreeLevel.MASTER,
    "masters": DegreeLevel.MASTER,
    "msc": DegreeLevel.MASTER,
    "ms": DegreeLevel.MASTER,
    "meng": DegreeLevel.MASTER,
    "ma": DegreeLevel.MASTER,
    "mba": DegreeLevel.MASTER,
    "bachelor": DegreeLevel.BACHELOR,
    "bachelors": DegreeLevel.BACHELOR,
    "bsc": DegreeLevel.BACHELOR,
    "bs": DegreeLevel.BACHELOR,
    "ba": DegreeLevel.BACHELOR,
    "beng": DegreeLevel.BACHELOR,
    "btech": DegreeLevel.BACHELOR,
    "associate": DegreeLevel.ASSOCIATE,
    "aas": DegreeLevel.ASSOCIATE,
    "diploma": DegreeLevel.DIPLOMA,
    "bootcamp": DegreeLevel.BOOTCAMP,
}
_EDUCATION_LINE_RE = re.compile(
    r"(?P<deg>phd|doctorate|mphil|masters?|msc|meng|mba|bachelors?|bsc|beng|btech|bs|ba|associate|aas|diploma|bootcamp)",
    re.IGNORECASE,
)
_FIELD_RE = re.compile(
    r"(?:\bin\b|\bof\b)\s+(?P<field>[A-Z][A-Za-z&/ ]{2,48})", re.IGNORECASE
)
_INSTITUTION_RE = re.compile(
    r"\b(?P<inst>[A-Z][\w.&' ]{2,60}?(?:University|College|Institute|School|Academy|Polytechnic))\b"
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_education_items(segmentation, full_text: str) -> list[EducationItem]:
    from app.candidate.text_sections import ResumeSectionKind, section_of

    section = section_of(segmentation, ResumeSectionKind.EDUCATION)
    search_texts = [section.text] if section is not None else []
    search_texts.append(full_text)

    items: list[EducationItem] = []
    seen: set[str] = set()
    for candidate_text in search_texts:
        for line in candidate_text.split("\n"):
            degree_match = _EDUCATION_LINE_RE.search(line)
            if degree_match is None:
                continue
            degree_raw = degree_match.group("deg").lower()
            level = _DEGREE_MAP.get(degree_raw)
            canonical = level.value if level else degree_raw

            field_match = _FIELD_RE.search(line)
            field_of_study = (
                field_match.group("field").strip().rstrip(",.;")
                if field_match
                else None
            )
            institution_match = _INSTITUTION_RE.search(line)
            years = [int(y) for y in _YEAR_RE.findall(line)]
            graduation_year = max(years) if years else None

            key = f"{canonical}:{(field_of_study or '').lower()}:{institution_match.group('inst').lower() if institution_match else ''}"
            if key in seen:
                continue
            seen.add(key)
            items.append(
                EducationItem(
                    degree=canonical,
                    degree_raw=degree_raw,
                    field_of_study=field_of_study,
                    institution=(
                        institution_match.group("inst").strip()
                        if institution_match
                        else None
                    ),
                    graduation_year=graduation_year,
                    evidence=Evidence(
                        text=line.strip()[:200],
                        field="resume.education",
                        confidence=Confidence.MEDIUM,
                    ),
                )
            )
        if items:
            break
    return items


# ---------------------------------------------------------------------------
# Certifications (local deterministic vocabulary)
# ---------------------------------------------------------------------------

_CERT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("aws certified solutions architect", "AWS Certified Solutions Architect"),
    ("aws certified cloud practitioner", "AWS Certified Cloud Practitioner"),
    ("aws certified developer", "AWS Certified Developer"),
    ("azure certified", "Azure Certified"),
    ("google cloud certified", "Google Cloud Certified"),
    ("certified kubernetes administrator", "Certified Kubernetes Administrator"),
    ("cka", "Certified Kubernetes Administrator (CKA)"),
    ("project management professional", "Project Management Professional"),
    ("pmp", "Project Management Professional (PMP)"),
    ("certified scrum master", "Certified Scrum Master"),
    ("csm", "Certified Scrum Master (CSM)"),
    ("cissp", "CISSP"),
)


def extract_certification_items(full_text: str) -> list[CertificationItem]:
    lowered = full_text.lower()
    items: list[CertificationItem] = []
    seen: set[str] = set()
    for needle, display in _CERT_PATTERNS:
        position = lowered.find(needle)
        if position >= 0 and display not in seen:
            seen.add(display)
            items.append(
                CertificationItem(
                    name=display,
                    evidence=Evidence(
                        text=full_text[position:position + len(needle)],
                        field="resume.certifications",
                        confidence=Confidence.HIGH,
                    ),
                )
            )
    return items


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def extract_project_items(segmentation) -> list[ProjectItem]:
    from app.candidate.text_sections import ResumeSectionKind, section_of

    section = section_of(segmentation, ResumeSectionKind.PROJECTS)
    if section is None:
        return []
    items: list[ProjectItem] = []
    for block in section.blocks:
        lines = [line.strip() for line in block.text.split("\n") if line.strip()]
        if not lines:
            continue
        name = lines[0].lstrip("-•*·–— ").strip()
        description = " ".join(lines[1:]).strip() or None
        url = None
        url_match = _URL_RE.search(block.text)
        if url_match is not None:
            url = url_match.group(0)
            description = (description or "").replace(url, "").strip() or None
        technologies = _skills_from_text(block.text)
        items.append(
            ProjectItem(
                name=name or None,
                description=description,
                url=url,
                technologies=technologies,
                evidence=Evidence(
                    text=name[:120], field="resume.projects", confidence=Confidence.HIGH
                ),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Preferences (explicit statements only)
# ---------------------------------------------------------------------------

_PREF_CUES = {
    "relocation": ("willing to relocate", "open to relocation", "ready to relocate"),
    "remote": ("open to remote", "seeking remote", "remote work preferred",
               "interested in remote"),
}


def extract_preferences(full_text: str) -> PreferencesInfo:
    lowered = full_text.lower()
    info = PreferencesInfo()
    evidence: list[Evidence] = []

    if any(cue in lowered for cue in _PREF_CUES["relocation"]):
        info.relocation = True
        evidence.append(Evidence(text="willing to relocate", field="resume.preferences"))
    if any(cue in lowered for cue in _PREF_CUES["remote"]):
        info.remote = True
        evidence.append(Evidence(text="open to remote", field="resume.preferences"))

    for employment_type in EmploymentType:
        token = employment_type.value.replace("_", "-")
        pattern = rf"(?:seeking|looking for|interested in)\s+(?:an?\s+)?{re.escape(token)}"
        if re.search(pattern, lowered):
            info.employment_types.append(employment_type.value)
            evidence.append(
                Evidence(text=f"seeking {token}", field="resume.preferences")
            )

    location_match = re.search(
        r"preferred locations?\s*[:\-]\s*(?P<locs>[^\n]+)", lowered
    )
    if location_match:
        info.locations = [
            part.strip().title()
            for part in location_match.group("locs").split(",")
            if part.strip()
        ][:6]

    salary_match = re.search(
        r"(?:expected salary|salary expectation)s?\s*[:\-]?\s*"
        r"(?P<cur>[$€£₹])?\s?(?P<amt>\d[\d,]*)(?:\s?k)?",
        lowered,
    )
    if salary_match:
        amount_raw = salary_match.group("amt").replace(",", "")
        try:
            amount = float(amount_raw)
            if amount < 1000:
                amount *= 1000.0
            currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
            info.salary_min = SalaryPreference(
                amount=amount,
                currency=currency_map.get(salary_match.group("cur")) if salary_match.group("cur") else None,
            )
            evidence.append(
                Evidence(
                    text=salary_match.group(0),
                    field="resume.preferences",
                    confidence=Confidence.MEDIUM,
                )
            )
        except ValueError:
            pass

    if evidence:
        info.status = ExtractionStatus.EXPLICIT
        info.evidence = evidence
    return info


__all__ = [
    "extract_certification_items",
    "extract_contact",
    "extract_education_items",
    "extract_experience_field",
    "extract_identity",
    "extract_preferences",
    "extract_project_items",
    "extract_skills_field",
    "parse_date_token",
]
