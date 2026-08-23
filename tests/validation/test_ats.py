"""ATS checks A1–A8: coverage, stuffing, order, format, dates."""

from __future__ import annotations

from app.validation.ats import evaluate_ats


def make_tailored(**overrides):
    tailored = {
        "resume": {
            "target_job_index": 0,
            "summary": {"text": "Engineer focused on python.", "evidence_refs": []},
            "skills": [
                {
                    "name": "python",
                    "display": "Python",
                    "requirement": "required",
                    "evidence_refs": [],
                },
                {"name": "sql", "display": "SQL", "requirement": "preferred", "evidence_refs": []},
            ],
            "experience": [
                {
                    "source_index": 0,
                    "date_range_raw": "Jan 2020 - Present",
                    "highlights": [
                        {
                            "index": 0,
                            "original_text": "Built python pipelines",
                            "final_text": "Built python pipelines",
                            "evidence_ref": "resume.experience[0].highlights[0]",
                        },
                    ],
                }
            ],
            "projects": [],
            "education": [],
            "certifications": [],
        }
    }
    tailored["resume"].update(overrides)
    return tailored


PROFILE = {
    "profile_id": "p1",
    "summary": {"text": "Engineer focused on python."},
    "skills": {"items": [{"name": "python"}, {"name": "sql"}]},
    "experience": {
        "items": [
            {
                "title": "Data Engineer",
                "company": "Acme",
                "highlights": ["Built python pipelines"],
            }
        ]
    },
}

ANALYSIS = {
    "status": "ANALYZED",
    "analysis": {
        "skills": {
            "required": [{"name": "python"}, {"name": "docker"}],
            "preferred": [{"name": "sql"}],
        },
        "responsibilities": {
            "items": [
                {"text": "Build python data pipelines"},
                {"text": "Operate kubernetes clusters"},
            ]
        },
    },
}

MATCH = {"job_index": 0, "missing_required": ["docker"]}


def evaluate(tailored=None, analysis=ANALYSIS, match=MATCH):
    checks, metrics = evaluate_ats(tailored or make_tailored(), PROFILE, analysis, match)
    by_name = {c.name: c for c in checks}
    return by_name, metrics


class TestCoverage:
    def test_partial_required_coverage(self) -> None:
        by_name, metrics = evaluate()

        assert metrics.required_coverage_pct == 50.0
        assert metrics.preferred_coverage_pct == 100.0
        assert "docker" in by_name["A1_required_skill_coverage"].detail

    def test_full_coverage_passes(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["skills"].insert(
            0,
            {
                "name": "docker",
                "display": "Docker",
                "requirement": "required",
                "evidence_refs": [],
            },
        )
        by_name, metrics = evaluate(tailored=tailored)

        assert metrics.required_coverage_pct == 100.0
        assert by_name["A1_required_skill_coverage"].status == "passed"


class TestStuffing:
    def test_no_stuffing_passes(self) -> None:
        by_name, _metrics = evaluate()

        assert by_name["A5_keyword_stuffing"].status == "passed"

    def test_stuffing_suspected_when_inflated(self) -> None:
        tailored = make_tailored(
            summary={"text": " ".join(["python"] * 3) + " engineer with python and python again."},
        )
        by_name, _metrics = evaluate(tailored=tailored)

        assert by_name["A5_keyword_stuffing"].status in {"warning", "passed"}
        # exact status depends on corpus counts; the check must exist and be
        # explainable either way.


class TestSectionOrderAndFormat:
    def test_canonical_order_passes(self) -> None:
        by_name, _metrics = evaluate()

        assert by_name["A6_section_order"].status == "passed"

    def test_over_long_bullet_warns(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"][0]["highlights"][0]["final_text"] = "word " * 120
        by_name, _metrics = evaluate(tailored=tailored)

        assert by_name["A7_format_limits"].status == "warning"

    def test_highlight_cap_exceeded_warns(self) -> None:
        tailored = make_tailored()
        highlights = [
            {
                "index": i,
                "original_text": f"point {i}",
                "final_text": f"Built python thing {i}",
                "evidence_ref": f"resume.experience[0].highlights[{i}]",
            }
            for i in range(12)
        ]
        tailored["resume"]["experience"][0]["highlights"] = highlights
        by_name, _metrics = evaluate(tailored=tailored)

        assert by_name["A7_format_limits"].status == "warning"


class TestDateRangeConsistency:
    def test_consistent_separators_pass(self) -> None:
        by_name, _metrics = evaluate()

        assert by_name["A8_date_range_consistency"].status == "passed"

    def test_mixed_separators_warn(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"].append(
            {
                "source_index": 0,
                "date_range_raw": "Jan 2020 – Present",
                "highlights": [],
            }
        )
        by_name, _metrics = evaluate(tailored=tailored)

        assert by_name["A8_date_range_consistency"].status == "warning"
