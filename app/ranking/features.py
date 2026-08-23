"""Deterministic feature extraction over canonical Job dicts.

Every feature traces to a VERIFIED canonical field or documented ``extra``
payload; nothing is inferred beyond declared token rules. Skill matching is
boundary-safe (``java`` never matches inside ``javascript``), version-
tolerant (``python 3.11`` matches ``python``), and cross-form (``node.js``
matches ``nodejs``) — all stdlib-only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.dedup.normalize import (
    location_key as dedup_location_key,
)
from app.dedup.normalize import (
    normalize_company,
    normalize_title,
)
from app.ranking.preferences import (
    EmploymentType,
    ExperienceLevel,
    detect_level,
    normalize_employment,
)

_TOKEN_RE = re.compile(r"[a-z0-9+#]+")
_VERSION_RE = re.compile(r"v?\d+(?:\.\d+)*")

_SKILL_FIELDS: tuple[str, ...] = (
    "description",
    "requirements",
    "responsibilities",
)


def _parse_datetime(value: Any) -> datetime | None:
    """Timezone-aware ISO datetimes only; naive/date-only values are None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@dataclass(frozen=True)
class _FieldTokens:
    name: str
    tokens: tuple[str, ...]
    squashed: tuple[str, ...]


@dataclass(frozen=True)
class SkillMatch:
    skill: str
    where: tuple[str, ...]
    count: int


@dataclass(frozen=True)
class JobFeatures:
    index: int
    source: str
    source_job_id: str

    title_key: str
    title_tokens: frozenset[str]
    company_key: str | None

    location_key: str | None
    location_known: bool
    is_remote: bool | None  # True / False / None (unknown)

    employment: EmploymentType | None
    level: ExperienceLevel | None

    skill_parts: tuple[_FieldTokens, ...]

    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None

    created_at: datetime | None
    discovered_at: datetime | None
    confidence_hint: str | None


def extract_features(job: Mapping[str, Any], index: int) -> JobFeatures:
    extra = job.get("extra") or {}
    title_key = normalize_title(job.get("title") or "")
    schedule_text = None
    detected = extra.get("detected_extensions")
    if isinstance(detected, dict):
        schedule_text = detected.get("schedule")

    raw_location = job.get("location")
    loc_key = dedup_location_key(raw_location)
    location_known = bool(loc_key)

    workplace_type = extra.get("workplace_type")
    workplace_lower = str(workplace_type).strip().lower() if isinstance(workplace_type, str) else ""

    is_remote: bool | None
    if loc_key == "remote":
        is_remote = True
    elif location_known:
        is_remote = False
    elif workplace_lower == "remote":
        is_remote = True
    elif workplace_lower in {"on-site", "onsite", "hybrid"}:
        is_remote = False
    else:
        is_remote = None

    employment = normalize_employment(job.get("employment_type"))
    if employment is None and isinstance(schedule_text, str):
        employment = normalize_employment(schedule_text)

    level = detect_level(job.get("title"), schedule_text)

    parts: list[_FieldTokens] = []
    for field_name in _SKILL_FIELDS:
        text = job.get(field_name)
        if isinstance(text, str) and text.strip():
            parts.append(_make_field_tokens(field_name, [text]))
    skills_value = extra.get("skills")
    if isinstance(skills_value, str) and skills_value.strip():
        parts.append(_make_field_tokens("extra.skills", [skills_value]))
    highlights = extra.get("job_highlights")
    if isinstance(highlights, list):
        items = []
        for highlight in highlights:
            if not isinstance(highlight, dict):
                continue
            raw_items = highlight.get("items")
            if not isinstance(raw_items, list):
                continue
            items.extend(item for item in raw_items if isinstance(item, str))
        if items:
            parts.append(_make_field_tokens("extra.job_highlights", items))

    salary_min = salary_max = None
    salary_currency = salary_period = None
    salary = job.get("salary")
    if isinstance(salary, dict):
        salary_min = _decimal(salary.get("min_amount"))
        salary_max = _decimal(salary.get("max_amount"))
        currency = salary.get("currency")
        salary_currency = currency.upper() if isinstance(currency, str) else None
        period = salary.get("period")
        salary_period = period if isinstance(period, str) else None

    confidence_hint = None
    extraction_info = extra.get("extraction")
    if isinstance(extraction_info, dict):
        hint = extraction_info.get("confidence")
        confidence_hint = hint if isinstance(hint, str) else None

    created_at = _parse_datetime(job.get("source_created_at"))

    return JobFeatures(
        index=index,
        source=job.get("source") or "",
        source_job_id=job.get("source_job_id") or "",
        title_key=title_key,
        title_tokens=frozenset(title_key.split()),
        company_key=normalize_company(job.get("company") or "") or None,
        location_key=loc_key,
        location_known=location_known,
        is_remote=is_remote,
        employment=employment,
        level=level,
        skill_parts=tuple(parts),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_period=salary_period,
        created_at=created_at,
        discovered_at=_parse_datetime(job.get("discovered_at")),
        confidence_hint=confidence_hint,
    )


def _make_field_tokens(name: str, texts: list[str]) -> _FieldTokens:
    lowered = "\n".join(text.lower() for text in texts if isinstance(text, str))
    tokens = tuple(_TOKEN_RE.findall(lowered))
    squashed = tuple(token.replace(".", "") for token in tokens)
    return _FieldTokens(name=name, tokens=tokens, squashed=squashed)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


# ---------------------------------------------------------------------------
# Skill matching (boundary-safe, version-tolerant, cross-form)
# ---------------------------------------------------------------------------


def find_skill(features: JobFeatures, skill: str) -> SkillMatch | None:
    needle_raw = skill.strip().lower()
    if not needle_raw:
        return None
    needle_tokens = [t for t in _TOKEN_RE.findall(needle_raw)]
    # Version tolerance on the needle itself ("python 3.11" -> "python").
    needle_core = [t for t in needle_tokens if not _VERSION_RE.fullmatch(t)] or needle_tokens
    n = len(needle_core)
    needle_squash = "".join(t.replace(".", "") for t in needle_core)

    where: list[str] = []
    total = 0
    for part in features.skill_parts:
        tokens, squashed = part.tokens, part.squashed
        i = 0
        length = len(tokens)
        while i < length:
            token, squash = tokens[i], squashed[i]

            # Fast path: a single haystack token equals the whole needle
            # once dots are squashed ("nodejs" == "node.js").
            if squash == needle_squash:
                where.append(part.name)
                total += 1
                i += 1
                continue

            if token != needle_core[0]:
                i += 1
                continue

            # Spaced-window walk with version-token tolerance.
            matched = 1
            j = i + 1
            while j < length and matched < n:
                next_token, next_squash = tokens[j], squashed[j]
                if _VERSION_RE.fullmatch(next_token):
                    j += 1
                    continue
                expected = needle_core[matched]
                if next_token == expected or next_squash == expected.replace(".", ""):
                    matched += 1
                    j += 1
                else:
                    break
            if matched == n:
                where.append(part.name)
                total += 1
                i = j
                continue
            i += 1

    if not where:
        return None
    return SkillMatch(skill=skill, where=tuple(where), count=total)


__all__ = ["JobFeatures", "SkillMatch", "extract_features", "find_skill"]
