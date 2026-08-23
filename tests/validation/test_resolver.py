"""Evidence-path resolver tests."""

from __future__ import annotations

from app.validation.resolver import (
    collect_evidence_refs,
    gather_evidence_corpus,
    resolve_path,
)


PROFILE = {
    "profile_id": "p1",
    "summary": {"text": "Data engineer."},
    "skills": {"items": [
        {"name": "python", "matched_as": "Python", "category": "language"},
        {"name": "sql", "matched_as": "SQL", "category": "language"},
    ]},
    "experience": {"items": [
        {"title": "DE", "company": "Acme",
         "date_range_raw": "Jan 2020 - Present",
         "highlights": ["Built pipelines", "Tuned postgres"]},
    ]},
    "projects": {"items": [
        {"name": "ETL", "description": "python etl", "url": None,
         "technologies": [{"name": "python"}]},
    ]},
    "education": {"items": [{"degree": "bachelor"}]},
    "certifications": {"items": [{"name": "AWS Certified Solutions Architect"}]},
}


class TestResolvePath:
    def test_skill_name_filter(self) -> None:
        found, value = resolve_path(PROFILE, "resume.skills.items[name=python]")

        assert found is True
        assert value["matched_as"] == "Python"

    def test_experience_index_and_attr(self) -> None:
        found, value = resolve_path(PROFILE, "resume.experience[0].title")
        assert found is True and value == "DE"

    def test_negative_index(self) -> None:
        found, value = resolve_path(PROFILE, "resume.experience[-1].company")
        assert found is True and value == "Acme"

    def test_highlight_index(self) -> None:
        found, value = resolve_path(
            PROFILE, "resume.experience[0].highlights[1]"
        )
        assert found is True and value == "Tuned postgres"

    def test_cert_name_with_spaces(self) -> None:
        found, value = resolve_path(PROFILE, "resume.certifications.items[name=aws certified solutions architect]")
        assert found is True
        assert value["name"].startswith("AWS")

    def test_summary_text(self) -> None:
        found, value = resolve_path(PROFILE, "resume.summary.text")
        assert found is True and value == "Data engineer."

    def test_unresolvable_paths_return_false(self) -> None:
        for bad in (
            "",
            "jobs[0]",
            "resume.skills.items[name=java]",
            "resume.experience[9].title",
            "resume.experience.title.deep",
            "resume.contact.emails",
        ):
            found, _value = resolve_path(PROFILE, bad)
            assert found is False, bad

    def test_never_raises_on_garbage(self) -> None:
        for garbage in (None, 123, ["x"], "resume..a", "resume.[0]", ".."):
            found, _value = resolve_path(PROFILE, garbage)
            assert found is False


class TestCorpusAndRefs:
    def test_corpus_covers_all_authored_text(self) -> None:
        corpus = gather_evidence_corpus(PROFILE)

        joined = " ".join(corpus).lower()
        for expected in ("data engineer", "built pipelines", "python",
                         "aws certified"):
            assert expected in joined

    def test_collect_refs_walks_all_sections(self) -> None:
        tailored = {
            "summary": {"evidence_refs": ["resume.summary.text"]},
            "skills": [{"evidence_refs": ["resume.skills.items[name=python]"]}],
            "experience": [{
                "evidence_refs": ["resume.experience[0]"],
                "highlights": [{"evidence_ref":
                                "resume.experience[0].highlights[0]"}],
            }],
            "projects": [{"evidence_ref": "resume.projects[0]"}],
            "education": [{"evidence_ref": "resume.education.items[0]"}],
            "certifications": [{"evidence_ref": "resume.certifications.items[name=aws certified solutions architect]"}],
            "changes": [{"operation": "skill_priority", "section": "skills",
                         "reason": "r", "evidence_refs": [
                             "resume.skills.items[name=sql]"]}],
        }
        refs = collect_evidence_refs(tailored)

        assert len(refs) == 7
        assert all(isinstance(ref, str) and ref for ref in refs)
