"""Validation orchestration: severity aggregation, confidence, skip."""

from __future__ import annotations

from app.validation.service import validate_resume
from tests.validation.test_ats import PROFILE
from tests.validation.test_ats import make_tailored as make_good_tailored

# Required set fully covered by the make_tailored fixture => clean PASS run.
ANALYSIS = {
    "status": "ANALYZED",
    "job_index": 0,
    "analysis": {"skills": {"required": [{"name": "python"}]}},
}
MATCH = {"job_index": 0, "missing_required": []}


def run(tailored=None, profile=PROFILE):
    tailored_result = (
        tailored
        if tailored is not None
        else {
            **make_good_tailored(),
        }
    )
    return validate_resume(
        tailored_result,
        {"status": "PARSED", "profile": profile},
        [MATCH],
        [ANALYSIS],
        [{"source": "greenhouse"}],
    )


class TestSeverityAggregation:
    def test_clean_run_passes(self) -> None:
        outcome = run()

        assert outcome.report.overall_status == "PASS"
        assert outcome.report.confidence == "high"

    def test_truth_failure_makes_overall_fail(self) -> None:
        tailored = {
            "status": "tailored",
            "resume": {
                "target_job_index": 0,
                "source_profile_id": "p1",
                "summary": {"text": "Expert in pytorch kubernetes rust.", "evidence_refs": []},
                "skills": [],
                "experience": [],
                "projects": [],
                "education": [],
                "certifications": [],
                "changes": [],
                "unaddressed_jd_requirements": [],
                "warnings": [],
            },
        }
        outcome = run(tailored=tailored)

        assert outcome.report.overall_status == "FAIL"
        assert any(c.status == "failed" for c in outcome.report.truth.checks)
        assert outcome.report.confidence == "low"

    def test_ats_warning_caps_at_warn(self) -> None:
        tailored = make_good_tailored()
        # over-long bullet triggers an A7 warning only (tokens stay in evidence)
        tailored["resume"]["experience"][0]["highlights"][0]["final_text"] = "pipelines " * 130
        outcome = run(tailored=tailored)

        assert outcome.report.overall_status == "WARN"
        assert not any(c.status == "failed" for c in outcome.report.truth.checks)


class TestMetrics:
    def test_metrics_present_and_explainable(self) -> None:
        outcome = run()

        metrics = outcome.report.ats.metrics
        assert metrics is not None
        assert 0 <= metrics.required_coverage_pct <= 100
        assert isinstance(metrics.keyword_counts, list)
        python_entry = next((k for k in metrics.keyword_counts if k.term == "python"), None)
        assert python_entry is not None


class TestDeterminism:
    def test_repeat_runs_identical(self) -> None:
        first = run().report.to_dict()
        second = run().report.to_dict()

        for section in ("truth", "ats"):
            for _check_first in first[section]["checks"]:
                pass  # structure identical; compare serialized forms below
        assert first == second
