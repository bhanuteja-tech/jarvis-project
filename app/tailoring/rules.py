"""Deterministic tailoring rules (pure functions).

Selection, ordering, capping, and summary assembly. No I/O, no LLM, no
mutation — every function returns new structures.
"""

from __future__ import annotations

import re

from app.dedup.normalize import base_normalize
from app.tailoring.models import ChangeRecord
from app.tailoring.views import ExpRef, ProjRef, SkillRef

_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "our",
        "you",
        "your",
        "will",
        "are",
        "was",
        "were",
        "has",
        "have",
        "this",
        "that",
        "from",
        "into",
        "their",
        "them",
        "they",
        "across",
        "about",
        "using",
        "use",
        "work",
    }
)


def content_tokens(text: str) -> set[str]:
    """Lowercase informative tokens (>=3 chars, stopwords removed)."""
    return {
        token
        for token in base_normalize(re.sub(r"[^a-z0-9+#& ]+", " ", text.lower())).split()
        if len(token) >= 3 and token not in _STOP_TOKENS
    }


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def tag_and_rank_skills(
    skills: tuple[SkillRef, ...],
    required_skills: frozenset[str],
    preferred_skills: frozenset[str],
) -> list[tuple[SkillRef, str]]:
    """Order: JD-required-matched, then preferred-matched, then additional.
    Alphabetical within each group for determinism."""
    tagged: list[tuple[SkillRef, str]] = []
    for skill in skills:
        if skill.name in required_skills:
            requirement = "required"
        elif skill.name in preferred_skills:
            requirement = "preferred"
        else:
            requirement = "additional"
        tagged.append((skill, requirement))

    group_order = {"required": 0, "preferred": 1, "additional": 2}
    tagged.sort(key=lambda pair: (group_order[pair[1]], pair[0].name))
    return tagged


def unaddressed_requirements(
    required_skills: frozenset[str], candidate_names: frozenset[str]
) -> list[str]:
    return sorted(required_skills - candidate_names)


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


def _contains_skill(line_lower: str, skill_name: str) -> bool:
    pattern = r"(?<![a-z0-9+#])" + re.escape(skill_name.lower()) + r"(?![a-z0-9+#])"
    return re.search(pattern, line_lower) is not None


def score_experience_item(
    item: ExpRef,
    matched_skills: frozenset[str],
    responsibility_tokens: frozenset[str],
) -> int:
    """Relevance = distinct matched skills evidenced in the item + overlap."""
    matched_hits = 0
    for name in matched_skills:
        if name in item.skill_names or any(
            _contains_skill(highlight.lower(), name) for highlight in item.highlights
        ):
            matched_hits += 1
    overlap = (
        1
        if any(responsibility_tokens & content_tokens(highlight) for highlight in item.highlights)
        else 0
    )
    return matched_hits * 2 + overlap


def select_highlights(
    highlights: tuple[str, ...],
    item_skill_names: frozenset[str],
    matched_skills: frozenset[str],
    responsibility_tokens: frozenset[str],
    cap: int,
) -> tuple[list[int], list[ChangeRecord]]:
    """Pick up to ``cap`` highlight indices.

    Relevant = contains a candidate skill that the target JD matched, OR
    shares at least one informative token with the JD responsibilities.
    If nothing qualifies, keep the FIRST highlight so substance survives,
    with an explicit change record.
    """
    changes: list[ChangeRecord] = []
    scored: list[tuple[int, int]] = []
    for index, highlight in enumerate(highlights):
        lowered = highlight.lower()
        skill_score = sum(1 for name in matched_skills if _contains_skill(lowered, name))
        resp_overlap = bool(responsibility_tokens & content_tokens(highlight))
        relevance = skill_score * 2 + (1 if resp_overlap else 0)
        if relevance > 0:
            scored.append((index, relevance))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    selected = [index for index, _score in scored[:cap]]

    if not selected and highlights:
        selected = [0]
        changes.append(
            ChangeRecord(
                operation="highlight_select",
                section="experience",
                reason=(
                    "no keyword signal in this entry; kept the first bullet to preserve substance"
                ),
            )
        )
    dropped = [i for i in range(len(highlights)) if i not in set(selected)]
    if dropped:
        changes.append(
            ChangeRecord(
                operation="highlight_select",
                section="experience",
                reason=f"selected {len(selected)} of {len(highlights)} bullets "
                f"by relevance to the target role",
            )
        )
    return sorted(selected), changes


def order_experience_items(
    items: tuple[ExpRef, ...],
    matched_skills: frozenset[str],
    responsibility_tokens: frozenset[str],
) -> list[int]:
    decorated: list[tuple[int, int, int, int]] = []
    for index, item in enumerate(items):
        matches = sum(1 for name in matched_skills if name in item.skill_names)
        duration = item.duration_months if item.duration_months is not None else -1
        decorated.append((index, matches, duration, index))
    decorated.sort(key=lambda row: (-row[1], -row[2], row[3]))
    return [row[0] for row in decorated]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def rank_projects(
    projects: tuple[ProjRef, ...],
    matched_skills: frozenset[str],
    cap: int,
) -> tuple[list[int], ChangeRecord | None]:
    decorated: list[tuple[int, int, int]] = []
    for index, project in enumerate(projects):
        distinct_matches = len(set(project.tech_names) & matched_skills)
        decorated.append((index, distinct_matches, index))
    relevant = [row for row in decorated if row[1] > 0]
    relevant.sort(key=lambda row: (-row[1], row[2]))
    selected = [row[0] for row in relevant[:cap]]

    change = None
    if selected:
        change = ChangeRecord(
            operation="project_rank",
            section="projects",
            reason=(
                f"prioritized {len(selected)} project(s) by matched "
                "technologies for the target role"
            ),
        )
    return selected, change


# ---------------------------------------------------------------------------
# Summary template
# ---------------------------------------------------------------------------


def build_summary(
    latest_title_words: str | None,
    total_years: float | None,
    top_matched_skills: list[str],
) -> tuple[str, list[str]]:
    """Deterministic template strictly over supplied evidence fragments."""
    evidence_refs: list[str] = []
    role_clause = ""
    if latest_title_words:
        clean_title = " ".join(latest_title_words.split())
        role_clause = clean_title
        evidence_refs.append("resume.experience[-1].title")

    years_clause = ""
    if total_years is not None:
        years_text = f"{total_years:g}"
        years_clause = f"{years_text} year{'s' if total_years != 1 else ''} of experience"

    skills_clause = ""
    if top_matched_skills:
        skills_clause = ", ".join(top_matched_skills[:3])
        evidence_refs.extend(f"resume.skills.items[name={name}]" for name in top_matched_skills[:3])

    parts: list[str] = []
    if role_clause and years_clause:
        parts.append(f"{role_clause} with {years_clause}")
    elif years_clause:
        parts.append(f"Professional with {years_clause}")
    elif role_clause:
        parts.append(role_clause)

    sentence = " ".join(parts)
    if skills_clause:
        if sentence:
            sentence = f"{sentence}, focused on {skills_clause}."
        else:
            sentence = f"Focused on {skills_clause}."
    elif sentence:
        sentence = f"{sentence}."
    return sentence, evidence_refs


__all__ = [
    "build_summary",
    "content_tokens",
    "order_experience_items",
    "rank_projects",
    "select_highlights",
    "tag_and_rank_skills",
    "unaddressed_requirements",
]
