"""Truth checks T1–T10: containment, fidelity, refs, skills, insertion,
consistency, duplicates, PII, metadata."""

from __future__ import annotations

from app.validation.truth import run_truth_checks


def make_tailored(**overrides):
    tailored = {
        "resume": {
            "target_job_index": 0,
            "target_job_ref": {"source": "greenhouse", "source_job_id": "1"},
            "source_profile_id": "p1",
            "summary": {
                "text": "Data Engineer, focused on python.",
                "evidence_refs": ["resume.experience.items[0].title"],
            },
            "skills": [
                {
                    "name": "python",
                    "display": "Python",
                    "requirement": "required",
                    "evidence_refs": ["resume.skills.items[name=python]"],
                }
            ],
            "experience": [
                {
                    "source_index": 0,
                    "title": "DE",
                    "company": "Acme",
                    "date_range_raw": "Jan 2020 - Present",
                    "highlights": [
                        {
                            "index": 0,
                            "original_text": "Built pipelines",
                            "final_text": "Built python pipelines",
                            "evidence_ref": "resume.experience.items[0].highlights[0]",
                        }
                    ],
                    "evidence_refs": ["resume.experience.items[0]"],
                }
            ],
            "projects": [],
            "education": [],
            "certifications": [],
            "changes": [],
            "unaddressed_jd_requirements": [],
        }
    }
    tailored["resume"].update(overrides)
    return tailored


PROFILE = {
    "profile_id": "p1",
    "summary": {"text": "Data engineer."},
    "skills": {
        "items": [
            {"name": "python", "matched_as": "Python"},
            {"name": "sql", "matched_as": "SQL"},
        ]
    },
    "experience": {
        "items": [
            {
                "title": "DE",
                "company": "Acme",
                "start_raw": "Jan 2020",
                "end_raw": "Present",
                "start_iso": "2020-01-01",
                "end_iso": None,
                "duration_months": None,
                "highlights": ["Built pipelines"],
            },
        ]
    },
    "projects": {"items": []},
    "education": {"items": [{"degree": "bachelor"}]},
    "certifications": {"items": []},
}

ANALYSIS = {
    "status": "ANALYZED",
    "analysis": {
        "skills": {"required": [{"name": "python"}], "preferred": []},
    },
}

MATCH = {
    "job_index": 0,
    "matched_skills": ["python"],
    "missing_required": [],
}


def checks_by_name(tailored, profile=PROFILE, analysis=ANALYSIS, match=MATCH):
    return {c.name: c for c in run_truth_checks(tailored, profile, analysis, match)}


class TestT1Containment:
    def test_contained_passes(self) -> None:
        result = checks_by_name(make_tailored())
        assert result["T1_token_containment"].status == "passed"

    def test_fabricated_token_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["summary"]["text"] = (
            "Expert in pytorch kubernetes rust at planetary scale"
        )
        result = checks_by_name(tailored)

        assert result["T1_token_containment"].status == "failed"
        assert "pytorch" in result["T1_token_containment"].detail

    def test_bullet_fabrication_fails(self) -> None:
        tailored = make_tailored()
        bullet = tailored["resume"]["experience"][0]["highlights"][0]
        bullet["final_text"] = "Serving 1M users with pytorch"
        result = checks_by_name(tailored)

        assert result["T1_token_containment"].status == "failed"


class TestT2Fidelity:
    def test_original_drift_detected(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"][0]["highlights"][0]["original_text"] = (
            "Completely different text"
        )
        result = checks_by_name(tailored)

        assert result["T2_original_fidelity"].status == "failed"
        assert "drift" in result["T2_original_fidelity"].detail.lower()


class TestT3Refs:
    def test_all_refs_resolve(self) -> None:
        result = checks_by_name(make_tailored())

        assert result["T3_evidence_refs_resolvable"].status == "passed"

    def test_unresolvable_ref_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["skills"][0]["evidence_refs"] = ["resume.skills.items[name=java]"]
        result = checks_by_name(tailored)

        assert result["T3_evidence_refs_resolvable"].status == "failed"


class TestT4Skills:
    def test_supported_skill_passes(self) -> None:
        result = checks_by_name(make_tailored())

        assert result["T4_unsupported_skills"].status == "passed"

    def test_unsupported_skill_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["skills"].append(
            {
                "name": "pytorch",
                "display": "PyTorch",
                "requirement": "additional",
                "evidence_refs": [],
            }
        )
        result = checks_by_name(tailored)

        assert result["T4_unsupported_skills"].status == "failed"
        assert "pytorch" in result["T4_unsupported_skills"].detail


class TestT5InsertionGuard:
    def test_missing_required_inserted_fails(self) -> None:
        match_with_missing = {**MATCH, "missing_required": ["kubernetes"]}
        tailored = make_tailored()
        tailored["resume"]["skills"].append(
            {
                "name": "kubernetes",
                "display": "Kubernetes",
                "requirement": "additional",
                "evidence_refs": [],
            }
        )
        result = checks_by_name(tailored, match=match_with_missing)

        assert result["T5_missing_skills_not_inserted"].status == "failed"

    def test_unaddressed_list_never_appears_in_output(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["unaddressed_jd_requirements"] = ["docker"]
        # docker not present as a skill => pass
        result = checks_by_name(tailored)

        assert result["T5_missing_skills_not_inserted"].status == "passed"

    def test_skill_present_but_also_unaddressed_is_contradiction(self) -> None:
        match_with_missing = {**MATCH, "missing_required": ["docker"]}
        tailored = make_tailored()
        tailored["resume"]["unaddressed_jd_requirements"] = ["docker"]
        tailored["resume"]["skills"].append(
            {
                "name": "docker",
                "display": "Docker",
                "requirement": "additional",
                "evidence_refs": [],
            }
        )
        result = checks_by_name(tailored, match=match_with_missing)

        # docker was inserted despite being listed missing
        assert result["T5_missing_skills_not_inserted"].status == "failed"


class TestT6Consistency:
    def test_consistent_passthrough(self) -> None:
        result = checks_by_name(make_tailored())

        assert result["T6_employer_title_date_consistency"].status == "passed"

    def test_title_change_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"][0]["title"] = "VP of Engineering"
        result = checks_by_name(tailored)

        assert result["T6_employer_title_date_consistency"].status == "failed"

    def test_company_change_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"][0]["company"] = "Other Corp"
        result = checks_by_name(tailored)

        assert result["T6_employer_title_date_consistency"].status == "failed"

    def test_invalid_source_index_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["experience"][0]["source_index"] = 99
        result = checks_by_name(tailored)

        assert result["T6_employer_title_date_consistency"].status == "failed"


class TestT8Duplicates:
    def test_duplicate_bullets_fail(self) -> None:
        tailored = make_tailored()
        dup = dict(tailored["resume"]["experience"][0]["highlights"][0])
        tailored["resume"]["experience"][0]["highlights"].append(dup)
        result = checks_by_name(tailored)

        assert result["T8_duplicate_content"].status == "failed"


class TestT9PII:
    def test_clean_resume_passes(self) -> None:
        result = checks_by_name(make_tailored())

        assert result["T9_pii_absence"].status == "passed"

    def test_email_leak_fails_without_exposing_value(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["summary"]["text"] = "Reach me at secret@corp.com please"
        result = checks_by_name(tailored)

        assert result["T9_pii_absence"].status == "failed"
        assert "secret@corp.com" not in result["T9_pii_absence"].detail
        assert "count=" in result["T9_pii_absence"].detail


class TestT10Meta:
    def test_llm_rewrite_implies_not_deterministic(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["changes"].append(
            {
                "operation": "bullet_rewrite_llm",
                "section": "experience[0]",
                "reason": "rewritten",
                "evidence_refs": [],
            }
        )
        # deterministic_only stays True => inconsistency
        result = checks_by_name(tailored)

        assert result["T10_meta_consistency"].status == "failed"

    def test_profile_id_mismatch_fails(self) -> None:
        tailored = make_tailored()
        tailored["resume"]["source_profile_id"] = "different-profile"
        result = checks_by_name(tailored)

        assert result["T10_meta_consistency"].status == "failed"
