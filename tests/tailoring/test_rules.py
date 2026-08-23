"""Deterministic tailoring rules: tagging, ordering, selection, summary."""

from __future__ import annotations

from app.tailoring.rules import (
    build_summary,
    order_experience_items,
    rank_projects,
    select_highlights,
    tag_and_rank_skills,
    unaddressed_requirements,
)
from app.tailoring.views import ExpRef, ProjRef, SkillRef


def skill(name, display=None):
    return SkillRef(name=name, display=display or name.title())


def exp(index, highlights=(), skill_names=(), duration_months=None, title="Engineer"):
    return ExpRef(
        index=index,
        title=title,
        company="Acme",
        date_range="Jan 2020 - Dec 2021",
        highlights=tuple(highlights),
        duration_months=duration_months,
        skill_names=frozenset(skill_names),
    )


class TestSkillTagging:
    def test_required_first_then_preferred_then_additional(self) -> None:
        tagged = tag_and_rank_skills(
            (skill("zookeeper"), skill("python"), skill("airflow"), skill("sql")),
            required_skills=frozenset({"python"}),
            preferred_skills=frozenset({"sql"}),
        )

        tags = [tag for _skill, tag in tagged]
        assert tags == ["required", "preferred", "additional", "additional"]

    def test_unaddressed_requirements(self) -> None:
        missing = unaddressed_requirements(frozenset({"python", "pytorch"}), frozenset({"python"}))

        assert missing == ["pytorch"]


class TestHighlightSelection:
    def test_relevant_bullets_kept_capped(self) -> None:
        highlights = (
            "Built python data pipelines",
            "Managed postgres cluster",
            "Answered support tickets",
            "Designed python ETL framework",
            "Wrote documentation",
        )
        indices, changes = select_highlights(
            highlights,
            item_skill_names=frozenset(),
            matched_skills=frozenset({"python"}),
            responsibility_tokens=frozenset({"pipelines"}),
            cap=2,
        )

        assert indices == [0, 3]
        assert any(change.operation == "highlight_select" for change in changes)

    def test_no_relevant_keeps_first_with_note(self) -> None:
        indices, changes = select_highlights(
            ("Answered phones", "Filed papers"),
            item_skill_names=frozenset(),
            matched_skills=frozenset({"python"}),
            responsibility_tokens=frozenset({"pipelines"}),
            cap=3,
        )

        assert indices == [0]
        assert any("no keyword signal" in change.reason for change in changes)


class TestExperienceOrdering:
    def test_matches_desc_then_duration_desc(self) -> None:
        items = (
            exp(0, skill_names=("rust",), duration_months=24),
            exp(1, skill_names=("python",), duration_months=36),
            exp(2, skill_names=("python", "sql"), duration_months=12),
        )

        order = order_experience_items(
            items,
            matched_skills=frozenset({"python", "sql"}),
            responsibility_tokens=frozenset(),
        )

        assert order == [2, 1, 0]


class TestProjectRanking:
    def test_matched_tech_first_capped(self) -> None:
        projects = (
            ProjRef(index=0, name="Game", description=None, url=None, tech_names=("rust",)),
            ProjRef(index=1, name="ETL", description=None, url=None, tech_names=("python", "sql")),
            ProjRef(index=2, name="Site", description=None, url=None, tech_names=("python",)),
        )

        selected, change = rank_projects(
            projects, matched_skills=frozenset({"python", "sql"}), cap=1
        )

        assert selected == [1]
        assert change is not None and "matched technologies" in change.reason

    def test_no_matched_projects_returns_empty(self) -> None:
        projects = (
            ProjRef(index=0, name="Game", description=None, url=None, tech_names=("rust",)),
        )

        selected, _change = rank_projects(projects, matched_skills=frozenset({"python"}), cap=3)

        assert selected == []


class TestSummaryTemplate:
    def test_full_template(self) -> None:
        text, refs = build_summary("Data Engineer", 6.0, ["python", "sql"])

        assert text == ("Data Engineer with 6 years of experience, focused on python, sql.")
        assert "resume.experience[-1].title" in refs

    def test_years_none_omits_clause(self) -> None:
        text, _refs = build_summary("Data Engineer", None, ["python"])

        assert text == "Data Engineer, focused on python."

    def test_no_evidence_yields_empty(self) -> None:
        text, _refs = build_summary(None, None, [])

        assert text == ""

    def test_singular_year_grammar(self) -> None:
        text, _refs = build_summary("Intern", 1.0, ["excel"])

        assert "1 year of experience" in text
