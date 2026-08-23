"""TailorView construction + target resolution over frozen dumps."""

from __future__ import annotations

from app.tailoring.views import build_profile_view, resolve_target


def make_candidate_result(**overrides):
    profile = {
        "profile_id": "pid-1",
        "skills": {"status": "explicit", "items": [
            {"name": "python", "matched_as": "Python", "category": "language"},
            {"name": "sql", "matched_as": "SQL", "category": "language"},
            {"name": "rust", "matched_as": "Rust", "category": "language"},
        ]},
        "experience": {"status": "explicit", "total_years": 6.0, "items": [
            {"title": "Data Engineer", "company": "Acme",
             "start_raw": "Jan 2021", "end_raw": "Present",
             "highlights": ["Built python pipelines", "Managed postgres cluster"]},
            {"title": "Analyst", "company": "Beta",
             "start_raw": "2018", "end_raw": "2020",
             "highlights": ["SQL reporting"]},
        ]},
        "projects": {"status": "explicit", "items": [
            {"name": "Warehouse", "description": "python etl", "url": None,
             "technologies": [{"name": "python", "matched_as": "python"}]},
            {"name": "Game", "description": "rust engine", "url": None,
             "technologies": [{"name": "rust", "matched_as": "rust"}]},
        ]},
        "education": {"items": [{"degree": "bachelor"}]},
        "certifications": {"items": [{"name": "AWS Certified Solutions Architect"}]},
        "summary": {"text": "Data engineer with python focus."},
    }
    profile.update(overrides)
    return {"status": "PARSED", "profile": profile}


MATCH = {
    "job_index": 0,
    "score": 80.0,
    "tier": "strong",
    "matched_skills": ["python", "sql"],
    "missing_required": ["docker"],
}


ANALYSIS = {
    "status": "ANALYZED",
    "job_index": 0,
    "analysis": {
        "skills": {
            "required": [{"name": "python"}, {"name": "sql"}, {"name": "docker"}],
            "preferred": [{"name": "airflow"}],
        },
        "responsibilities": {"items": [
            {"text": "Build python data pipelines"},
            {"text": "Operate postgres warehouses"},
        ]},
    },
}

JOBS = [{"source": "greenhouse", "source_job_id": "1",
         "title": "Data Engineer", "company": "TargetCo"}]


class TestProfileView:
    def test_usable_parse(self) -> None:
        view = build_profile_view(make_candidate_result())

        assert view.usable is True
        assert view.profile_id == "pid-1"
        names = {skill.name for skill in view.skills}
        assert {"python", "sql", "rust"} <= names
        displays = {skill.display for skill in view.skills}
        assert "Python" in displays

    def test_unusable_status(self) -> None:
        for status in ("SKIPPED", "FAILED"):
            view = build_profile_view({"status": status, "profile": None})
            assert view.usable is False

    def test_experience_highlights_and_dates(self) -> None:
        view = build_profile_view(make_candidate_result())

        first = view.experience[0]
        assert "Built python pipelines" in first.highlights
        assert first.date_range == "Jan 2021 - Present"


class TestTargetResolution:
    def test_default_top_match(self) -> None:
        resolution = resolve_target([MATCH], [ANALYSIS], JOBS, None)

        assert resolution.error_reason is None
        assert resolution.target.job_index == 0
        assert resolution.target.title == "Data Engineer"
        assert "docker" in resolution.target.required_skills
        assert "build python data pipelines" in \
            resolution.target.responsibilities_text.lower()

    def test_explicit_override_valid(self) -> None:
        resolution = resolve_target([MATCH], [ANALYSIS], JOBS, 0)

        assert resolution.target.job_index == 0

    def test_invalid_override_fails(self) -> None:
        resolution = resolve_target([MATCH], [ANALYSIS], JOBS, 9)

        assert resolution.error_reason == "invalid_target_job_index"

    def test_no_matches_fails(self) -> None:
        resolution = resolve_target([], [], JOBS, None)

        assert resolution.error_reason == "no_matches"
