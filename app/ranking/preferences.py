"""Structured user search preferences: explicit hard vs soft split.

- ``HardRequirements``  : failure eliminates the job from the ranked list.
- ``SoftPreferences``   : mismatch only lowers the relevance score.

Missing/unknown job data never triggers a hard rejection (locked principle);
hard filters record an evidence gap instead.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.dedup.normalize import normalize_title


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    OTHER = "other"


class ExperienceLevel(StrEnum):
    INTERN = "intern"
    FRESHER = "fresher"
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


#: Highest seniority first; detection returns the strongest signal present.
_LEVEL_LADDER: tuple[ExperienceLevel, ...] = (
    ExperienceLevel.PRINCIPAL,
    ExperienceLevel.LEAD,
    ExperienceLevel.SENIOR,
    ExperienceLevel.MID,
    ExperienceLevel.JUNIOR,
    ExperienceLevel.ENTRY,
    ExperienceLevel.FRESHER,
    ExperienceLevel.INTERN,
)

_EMPLOYMENT_PATTERNS: tuple[tuple[str, EmploymentType], ...] = (
    ("intern", EmploymentType.INTERNSHIP),
    ("co op", EmploymentType.INTERNSHIP),
    ("contract", EmploymentType.CONTRACT),
    ("temp", EmploymentType.TEMPORARY),
    ("part time", EmploymentType.PART_TIME),
    ("full time", EmploymentType.FULL_TIME),
)

_LEVEL_TOKEN_MAP: dict[str, ExperienceLevel] = {
    level.value: level for level in _LEVEL_LADDER
}
_LEVEL_TOKEN_MAP.update({"graduate": ExperienceLevel.ENTRY, "middle": ExperienceLevel.MID})


def normalize_employment(raw: Any) -> EmploymentType | None:
    """Map verified upstream variants onto the canonical employment enum."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = re.sub(r"[^a-z0-9]+", " ", raw.strip().lower()).strip()
    if not text:
        return None
    for needle, employment_type in _EMPLOYMENT_PATTERNS:
        if needle in text:
            return employment_type
    return EmploymentType.OTHER


def detect_level(*texts: Any) -> ExperienceLevel | None:
    """Detect the strongest seniority signal across supplied texts."""
    token_sets = [
        set(re.findall(r"[a-z]+", str(text).lower())) for text in texts if text
    ]
    for level in _LEVEL_LADDER:
        if any(level.value in tokens for tokens in token_sets):
            return level
    return None


#: Declared role alias table (verified examples); extensible constant only.
ROLE_ALIASES: dict[str, frozenset[str]] = {
    "machine learning engineer": frozenset(
        {"ml engineer", "machine learning developer", "ml developer"}
    ),
    "software engineer": frozenset({"swe", "software developer"}),
}


def role_variants(role: str) -> frozenset[str]:
    key = normalize_title(role)
    return frozenset({key, *ROLE_ALIASES.get(key, set())})


class HardRequirements(BaseModel):
    locations: list[str] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    experience_levels: list[ExperienceLevel] = Field(default_factory=list)
    max_age_hours: float | None = None
    exclude_companies: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


class SoftPreferences(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    workplace_types: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    salary_min: Decimal | None = None
    salary_currency: str = "USD"
    prefer_internship_fresher: bool = False
    freshness_boost_hours: float = 24.0
    limit: int = Field(default=50, ge=1, le=500)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _clean_skills(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class SearchPreferences(BaseModel):
    hard: HardRequirements = Field(default_factory=HardRequirements)
    soft: SoftPreferences = Field(default_factory=SoftPreferences)

    @classmethod
    def from_state(cls, raw: Mapping[str, Any] | None) -> SearchPreferences:
        """Tolerant construction from ``search_preferences['ranking']``."""
        if not isinstance(raw, Mapping) or not raw:
            return cls()
        hard_raw = _section(raw, "hard", _HARD_SECTION_KEYS)
        soft_raw = _section(raw, "soft", _SOFT_SECTION_KEYS)

        hard_raw["employment_types"] = [
            et.value
            for et in (normalize_employment(item) for item in hard_raw.get("employment_types", []))
            if et is not None and et is not EmploymentType.OTHER
        ]
        for key in ("locations", "exclude_companies", "exclude_keywords"):
            values = hard_raw.get(key)
            if isinstance(values, list):
                hard_raw[key] = [
                    item.strip().lower()
                    for item in values
                    if isinstance(item, str) and item.strip()
                ]
        levels_raw = []
        for item in hard_raw.get("experience_levels", []):
            token = re.findall(r"[a-z]+", str(item).lower())
            for candidate in token:
                level = _LEVEL_TOKEN_MAP.get(candidate)
                if level is not None:
                    levels_raw.append(level.value)
                    break
        hard_raw["experience_levels"] = levels_raw

        salary_min = soft_raw.get("salary_min")
        if salary_min is not None:
            try:
                soft_raw["salary_min"] = Decimal(str(salary_min))
            except (InvalidOperation, ValueError):
                soft_raw["salary_min"] = None

        return cls.model_validate({"hard": hard_raw, "soft": soft_raw})


_HARD_SECTION_KEYS = (
    "locations",
    "employment_types",
    "experience_levels",
    "max_age_hours",
    "exclude_companies",
    "exclude_keywords",
)
_SOFT_SECTION_KEYS = (
    "target_roles",
    "workplace_types",
    "required_skills",
    "preferred_skills",
    "salary_min",
    "salary_currency",
    "prefer_internship_fresher",
    "freshness_boost_hours",
    "limit",
)


def _section(raw: Mapping[str, Any], name: str, keys: tuple[str, ...]) -> dict[str, Any]:
    nested = raw.get(name)
    section = dict(nested) if isinstance(nested, Mapping) else {}
    for key in keys:  # tolerate flat preference keys as well
        if key in raw and key not in section:
            section[key] = raw[key]
    return {key: value for key, value in section.items() if value not in (None, "", [])}


__all__ = [
    "EmploymentType",
    "ExperienceLevel",
    "HardRequirements",
    "ROLE_ALIASES",
    "SearchPreferences",
    "SoftPreferences",
    "detect_level",
    "normalize_employment",
    "role_variants",
]
