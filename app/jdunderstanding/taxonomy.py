"""Curated skill taxonomy with alias-aware, boundary-safe matching.

The registry is a compact in-Python table: ``canonical name → (category,
aliases…)``. Matching compiles one longest-first alternation over every
name/alias with custom boundaries so:

- ``Java`` never matches inside ``JavaScript``;
- ``C`` never matches inside ``C++``;
- ``SQL`` never matches inside ``NoSQL``;
- ``React`` is suppressed inside ``React Native`` via negative context
  (React Native is its own entry and matches first by length);
- ``Python`` never matches ``Pythonic`` (boundary rule).

Negative-context phrases (e.g. ``react native`` around a React hit) are
checked within a small window and suppress the weaker hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.jdunderstanding.models import SkillCategory


@dataclass(frozen=True)
class SkillDef:
    canonical: str
    category: SkillCategory
    aliases: tuple[str, ...] = ()
    negative_context: tuple[str, ...] = ()


def _skill(canonical: str, category: SkillCategory, *aliases: str, not_near: tuple[str, ...] = ()) -> SkillDef:
    return SkillDef(canonical=canonical, category=category, aliases=aliases, negative_context=not_near)


_REGISTRY: tuple[SkillDef, ...] = (
    # --- programming languages ------------------------------------------
    _skill("python", SkillCategory.LANGUAGE),
    _skill("java", SkillCategory.LANGUAGE),
    _skill("javascript", SkillCategory.LANGUAGE, "js"),
    _skill("typescript", SkillCategory.LANGUAGE, "ts"),
    _skill("c", SkillCategory.LANGUAGE),
    _skill("c++", SkillCategory.LANGUAGE, "cpp"),
    _skill("c#", SkillCategory.LANGUAGE, "csharp"),
    _skill("go", SkillCategory.LANGUAGE, "golang"),
    _skill("rust", SkillCategory.LANGUAGE),
    _skill("ruby", SkillCategory.LANGUAGE),
    _skill("php", SkillCategory.LANGUAGE),
    _skill("swift", SkillCategory.LANGUAGE),
    _skill("kotlin", SkillCategory.LANGUAGE),
    _skill("scala", SkillCategory.LANGUAGE),
    _skill("r", SkillCategory.LANGUAGE, not_near=("rr",)),
    _skill("sql", SkillCategory.LANGUAGE),
    _skill("bash", SkillCategory.LANGUAGE, "shell scripting"),
    # --- frameworks / libraries -----------------------------------------
    _skill("pytorch", SkillCategory.FRAMEWORK, "torch"),
    _skill("tensorflow", SkillCategory.FRAMEWORK),
    _skill("keras", SkillCategory.FRAMEWORK),
    _skill("scikit-learn", SkillCategory.FRAMEWORK, "sklearn"),
    _skill("fastapi", SkillCategory.FRAMEWORK),
    _skill("flask", SkillCategory.FRAMEWORK),
    _skill("django", SkillCategory.FRAMEWORK),
    _skill("spring boot", SkillCategory.FRAMEWORK, "spring"),
    _skill("react", SkillCategory.FRAMEWORK, "reactjs", not_near=("react native",)),
    _skill("react native", SkillCategory.FRAMEWORK),
    _skill("next.js", SkillCategory.FRAMEWORK, "nextjs"),
    _skill("vue.js", SkillCategory.FRAMEWORK, "vuejs", "vue"),
    _skill("angular", SkillCategory.FRAMEWORK),
    _skill("node.js", SkillCategory.FRAMEWORK, "nodejs", "node"),
    _skill("express.js", SkillCategory.FRAMEWORK, "expressjs", "express"),
    _skill(".net", SkillCategory.FRAMEWORK, "dotnet"),
    _skill("rails", SkillCategory.FRAMEWORK, "ruby on rails"),
    # --- cloud / infrastructure -------------------------------------------
    _skill("aws", SkillCategory.CLOUD, "amazon web services"),
    _skill("azure", SkillCategory.CLOUD, "microsoft azure"),
    _skill("gcp", SkillCategory.CLOUD, "google cloud platform", "google cloud"),
    _skill("docker", SkillCategory.TOOL),
    _skill("kubernetes", SkillCategory.TOOL, "k8s"),
    _skill("terraform", SkillCategory.TOOL),
    # --- databases --------------------------------------------------------
    _skill("postgresql", SkillCategory.DATABASE, "postgres"),
    _skill("mysql", SkillCategory.DATABASE),
    _skill("mongodb", SkillCategory.DATABASE, "mongo"),
    _skill("redis", SkillCategory.DATABASE),
    _skill("elasticsearch", SkillCategory.DATABASE),
    _skill("snowflake", SkillCategory.DATABASE),
    _skill("bigquery", SkillCategory.DATABASE),
    _skill("dynamodb", SkillCategory.DATABASE),
    _skill("sqlite", SkillCategory.DATABASE),
    # --- tools ------------------------------------------------------------
    _skill("git", SkillCategory.TOOL, not_near=("github", "gitlab")),
    _skill("github", SkillCategory.TOOL),
    _skill("gitlab", SkillCategory.TOOL),
    _skill("jira", SkillCategory.TOOL),
    _skill("jenkins", SkillCategory.TOOL),
    _skill("airflow", SkillCategory.TOOL, "apache airflow"),
    _skill("kafka", SkillCategory.TOOL, "apache kafka"),
    _skill("spark", SkillCategory.TOOL, "apache spark"),
    _skill("tableau", SkillCategory.TOOL),
    _skill("power bi", SkillCategory.TOOL, "powerbi"),
    _skill("linux", SkillCategory.TOOL),
    # --- concepts -----------------------------------------------------------
    _skill("machine learning", SkillCategory.CONCEPT, "ml", not_near=("ml ops",)),
    _skill("mlops", SkillCategory.CONCEPT, "ml ops"),
    _skill("deep learning", SkillCategory.CONCEPT),
    _skill("nlp", SkillCategory.CONCEPT, "natural language processing"),
    _skill("computer vision", SkillCategory.CONCEPT),
    _skill("etl", SkillCategory.CONCEPT),
    _skill("data pipelines", SkillCategory.CONCEPT, "data pipeline"),
    _skill("ci/cd", SkillCategory.METHODOLOGY, "continuous integration"),
    _skill("microservices", SkillCategory.CONCEPT),
    _skill("rest apis", SkillCategory.CONCEPT, "restful api", "rest api", "restful services"),
    _skill("llm", SkillCategory.CONCEPT, "large language model", "large language models"),
    _skill("data science", SkillCategory.CONCEPT),
    _skill("ab testing", SkillCategory.METHODOLOGY, "a/b testing"),
    _skill("agile", SkillCategory.METHODOLOGY, "scrum"),
    # --- soft skills ----------------------------------------------------------
    _skill("communication", SkillCategory.SOFT_SKILL),
    _skill("leadership", SkillCategory.SOFT_SKILL),
    _skill("ownership", SkillCategory.SOFT_SKILL),
    _skill("collaboration", SkillCategory.SOFT_SKILL),
    _skill("problem solving", SkillCategory.SOFT_SKILL),
    _skill("mentorship", SkillCategory.SOFT_SKILL, "mentoring"),
)

_BOUNDARY_L = r"(?<![A-Za-z0-9+#])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#])"


def _build_pattern() -> re.Pattern[str]:
    names: list[str] = []
    lookup: dict[str, SkillDef] = {}
    for definition in _REGISTRY:
        for name in (definition.canonical, *definition.aliases):
            key = name.lower()
            names.append(re.escape(key))
            # Longest-first resolution when aliases overlap.
            existing = lookup.get(key)
            if existing is None or len(existing.canonical) <= len(definition.canonical):
                lookup[key] = definition
    pattern = "|".join(sorted(names, key=len, reverse=True))
    return re.compile(f"{_BOUNDARY_L}(?:{pattern}){_BOUNDARY_R}", re.IGNORECASE)


_SKILL_PATTERN = _build_pattern()


@dataclass(frozen=True)
class SkillHit:
    canonical: str
    matched_as: str
    category: SkillCategory
    start: int
    end: int


def find_skill_hits(text: str) -> list[SkillHit]:
    """All taxonomy hits inside ``text``, negative contexts removed."""
    hits: list[SkillHit] = []
    occupied: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < o_end and o_start < end for o_start, o_end in occupied)

    for match in sorted(_SKILL_PATTERN.finditer(text), key=lambda m: m.start()):
        start, end = match.start(), match.end()
        if overlaps(start, end):
            continue
        matched_name = match.group(0).lower()
        definition = None
        for candidate in _REGISTRY:
            if matched_name == candidate.canonical or matched_name in candidate.aliases:
                definition = candidate
                break
        if definition is None:  # pragma: no cover - registry invariant
            continue

        window_start = max(0, start - 30)
        window_end = min(len(text), end + 30)
        context = text[window_start:window_end].lower()
        if any(guard in context for guard in definition.negative_context):
            # Guard phrase nearby; the longer guarded entry will claim it.
            continue

        hits.append(
            SkillHit(
                canonical=definition.canonical,
                matched_as=match.group(0),
                category=definition.category,
                start=start,
                end=end,
            )
        )
        occupied.append((start, end))

    return hits


__all__ = ["SkillDef", "SkillHit", "find_skill_hits"]
