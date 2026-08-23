"""Feature extraction + boundary-safe skill matching."""

from __future__ import annotations

from app.ranking.features import extract_features, find_skill
from app.ranking.preferences import EmploymentType, ExperienceLevel


def make_job(**overrides):
    base = {
        "source": "lever",
        "source_job_id": "1",
        "title": "ML Engineer",
        "company": "Acme Inc",
        "location": "Remote",
        "description": "<p>Work on python and machine learning systems.</p>",
        "requirements": "3+ years experience with python",
        "responsibilities": None,
        "employment_type": None,
        "salary": None,
        "source_created_at": "2026-08-20T10:00:00Z",
        "discovered_at": "2026-08-22T10:00:00Z",
        "extra": {},
    }
    base.update(overrides)
    return base


class TestCoreFeatures:
    def test_title_and_company_keys(self) -> None:
        features = extract_features(make_job(), 0)

        assert features.title_key == "ml engineer"
        assert features.company_key == "acme"

    def test_remote_tri_state(self) -> None:
        remote = extract_features(make_job(location="Remote"), 0)
        city = extract_features(make_job(location="Austin, TX"), 0)
        unknown = extract_features(make_job(location=None), 0)

        assert remote.is_remote is True
        assert city.is_remote is False
        assert unknown.location_known is False

    def test_lever_workplace_type_fills_unknown(self) -> None:
        features = extract_features(
            make_job(
                location=None,
                extra={"workplace_type": "remote"},
            ),
            0,
        )

        assert features.is_remote is True

    def test_employment_from_field_and_schedule_fallback(self) -> None:
        direct = extract_features(make_job(employment_type="Regular Full Time (Salary)"), 0)
        via_schedule = extract_features(
            make_job(extra={"detected_extensions": {"schedule": "Internship"}}),
            0,
        )

        assert direct.employment is EmploymentType.FULL_TIME
        assert via_schedule.employment is EmploymentType.INTERNSHIP

    def test_level_from_title(self) -> None:
        senior = extract_features(make_job(title="Senior ML Engineer"), 0)

        assert senior.level is ExperienceLevel.SENIOR

    def test_naive_source_created_at_is_none(self) -> None:
        features = extract_features(make_job(source_created_at="2026-08-01T09:30:00"), 0)

        assert features.created_at is None


class TestSkillMatching:
    def test_simple_match_in_description(self) -> None:
        features = extract_features(make_job(), 0)

        match = find_skill(features, "python")

        assert match is not None
        assert match.where == ("description", "requirements")

    def test_java_never_matches_inside_javascript(self) -> None:
        features = extract_features(
            make_job(description="Deep knowledge of javascript required."), 0
        )

        assert find_skill(features, "java") is None

    def test_versioned_needle_matches_plain_text(self) -> None:
        features = extract_features(
            make_job(description="Experience with python 3.11 required."), 0
        )

        assert find_skill(features, "python 3.11") is not None
        assert find_skill(features, "python") is not None

    def test_node_dot_js_cross_form(self) -> None:
        features = extract_features(make_job(description="Familiarity with nodejs ecosystem."), 0)

        assert find_skill(features, "node.js") is not None

    def test_c_plus_plus_boundary_kept(self) -> None:
        features = extract_features(make_job(description="Strong c++ background required."), 0)

        assert find_skill(features, "c++") is not None
        assert find_skill(features, "c") is None

    def test_compound_phrase_whole_match(self) -> None:
        features = extract_features(
            make_job(description="You will build machine learning pipelines."), 0
        )

        assert find_skill(features, "machine learning") is not None
        assert find_skill(features, "machine") is not None  # single token exists

    def test_missing_skill_returns_none(self) -> None:
        features = extract_features(make_job(description="<p>sales role</p>"), 0)

        assert find_skill(features, "pytorch") is None

    def test_empty_skill_returns_none(self) -> None:
        features = extract_features(make_job(), 0)

        assert find_skill(features, "   ") is None
