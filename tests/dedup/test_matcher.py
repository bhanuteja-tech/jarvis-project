"""Matching rules R1-R3 and false-positive guards V1-V5."""

from __future__ import annotations

from app.dedup.matcher import decide, make_view


def make_job(**overrides):
    base = {
        "source": "greenhouse",
        "source_job_id": "1",
        "title": "Software Engineer",
        "company": "Acme Inc",
        "location": "New York, NY",
        "description": "<p>Build things</p>",
        "employment_type": None,
        "salary": None,
        "job_url": f"https://boards.greenhouse.io/acme/jobs/{overrides.get('source_job_id', '1')}",
        "apply_url": None,
        "extra": {},
    }
    base.update(overrides)
    return base


def view(job):
    return make_view(job, 0)


class TestR1UrlIdentity:
    def test_identical_url_merges_across_sources_despite_other_conflicts(self) -> None:
        a = make_job(
            source="searchapi",
            job_url="https://careers.acme.com/jobs/9?utm_source=google",
            location="London",
            employment_type="CONTRACT",
        )
        b = make_job(
            source="career_page",
            job_url="https://careers.acme.com/jobs/9/",
            location="New York, NY",
            employment_type="FULL_TIME",
        )

        decision = decide(view(a), view(b))

        assert decision.merged is True
        assert decision.rule == "R1_url_key"

    def test_different_urls_fall_through_to_other_tiers(self) -> None:
        a = make_job(source_job_id="1", job_url="https://acme.com/jobs/1")
        b = make_job(source_job_id="2", job_url="https://acme.com/jobs/2")

        decision = decide(view(a), view(b))

        # Not R1 (URLs differ), but identical triple keys merge via R2.
        assert decision.rule != "R1_url_key"
        assert decision.merged is True
        assert decision.rule == "R2_exact_keys"


class TestR2ExactKeys:
    def test_exact_triple_keys_merge(self) -> None:
        a = make_job(source="greenhouse", source_job_id="1")
        b = make_job(source="lever", source_job_id="L-7")

        decision = decide(view(a), view(b))

        assert decision.merged is True
        assert decision.rule == "R2_exact_keys"

    def test_missing_location_side_is_tolerated(self) -> None:
        a = make_job(location=None)
        b = make_job(source="lever", source_job_id="2")

        assert decide(view(a), view(b)).merged is True

    def test_application_url_difference_does_not_block_merge(self) -> None:
        a = make_job(apply_url="https://a.example.com/apply/1")
        b = make_job(source="lever", source_job_id="2", apply_url=None)

        assert decide(view(a), view(b)).merged is True


class TestGuardsVetoes:
    def test_v1_requisition_id_conflict_blocks_r2(self) -> None:
        a = make_job(extra={"internal_job_id": 111})
        b = make_job(source="lever", source_job_id="2", extra={"internal_job_id": 222})

        decision = decide(view(a), view(b))

        assert decision.merged is False
        assert decision.veto_reason == "V1_requisition_id_conflict"
        assert decision.candidate is True  # high-similarity non-merge

    def test_v1_ignores_disjoint_id_ecosystems(self) -> None:
        a = make_job(extra={"internal_job_id": 111})
        b = make_job(source="lever", source_job_id="2", extra={"jsonld_identifier": "x"})

        assert decide(view(a), view(b)).merged is True

    def test_v2_location_mismatch_blocks(self) -> None:
        a = make_job(location="New York, NY")
        b = make_job(source="lever", source_job_id="2", location="London, UK")

        decision = decide(view(a), view(b))

        assert decision.merged is False
        assert decision.veto_reason == "V2_location_mismatch"

    def test_v2_remote_vs_city_blocked(self) -> None:
        a = make_job(location="Remote")
        b = make_job(source="lever", source_job_id="2", location="Austin, TX")

        decision = decide(view(a), view(b))

        assert decision.veto_reason == "V2_location_mismatch"

    def test_v3_employment_type_conflict_blocks(self) -> None:
        a = make_job(employment_type="FULL_TIME")
        b = make_job(source="lever", source_job_id="2", employment_type="CONTRACT")

        decision = decide(view(a), view(b))

        assert decision.merged is False
        assert decision.veto_reason == "V3_employment_type_conflict"

    def test_salary_overlap_merges_and_disjoint_blocks(self) -> None:
        salary_a = {"min_amount": 100000, "max_amount": 140000,
                    "currency": "USD", "period": "year"}
        salary_overlap = {"min_amount": 130000, "max_amount": 160000,
                          "currency": "USD", "period": "year"}
        salary_far = {"min_amount": 300000, "max_amount": 320000,
                      "currency": "USD", "period": "year"}

        overlap = decide(
            view(make_job(salary=salary_a)),
            view(make_job(source="lever", source_job_id="2", salary=salary_overlap)),
        )
        disjoint = decide(
            view(make_job(salary=salary_a)),
            view(make_job(source="lever", source_job_id="3", salary=salary_far)),
        )

        assert overlap.merged is True
        assert disjoint.merged is False
        assert disjoint.veto_reason == "V4_salary_disjoint"

    def test_currency_mismatch_conservatively_blocks(self) -> None:
        usd = {"min_amount": 100, "max_amount": 120, "currency": "USD", "period": "hour"}
        eur = {"min_amount": 100, "max_amount": 120, "currency": "EUR", "period": "hour"}

        decision = decide(
            view(make_job(salary=usd)),
            view(make_job(source="lever", source_job_id="2", salary=eur)),
        )

        assert decision.merged is False

    def test_v5_long_dissimilar_descriptions_block(self) -> None:
        filler = lambda word: " ".join([word] * 150)  # noqa: E731
        a = make_job(description=filler("alpha") + " tail one")
        b = make_job(source="lever", source_job_id="2", description=filler("omega") + " tail two")

        decision = decide(view(a), view(b))

        assert decision.merged is False
        assert decision.veto_reason == "V5_description_dissimilar"

    def test_short_descriptions_skip_v5_guard(self) -> None:
        a = make_job(description="<p>short</p>")
        b = make_job(source="lever", source_job_id="2", description="different words entirely here")

        assert decide(view(a), view(b)).merged is True


class TestR3FuzzyTitle:
    def test_reordered_token_sets_merge(self) -> None:
        a = make_job(title="Python Developer Senior")
        b = make_job(source="lever", source_job_id="2", title="Senior Developer Python")

        decision = decide(view(a), view(b))

        assert decision.merged is True
        assert decision.rule == "R3_title_fuzzy"

    def test_below_jaccard_threshold_does_not_merge(self) -> None:
        """Mandated case: seniority differences keep records separate."""
        a = make_job(title="Software Engineer")
        b = make_job(source="lever", source_job_id="2", title="Senior Software Engineer")

        decision = decide(view(a), view(b))

        assert decision.merged is False

    def test_fuzzy_requires_location_compatibility(self) -> None:
        a = make_job(title="Python Developer Senior", location="Remote")
        b = make_job(
            source="lever",
            source_job_id="2",
            title="Senior Developer Python",
            location="Berlin",
        )

        assert decide(view(a), view(b)).merged is False


class TestWarningSemantics:
    def test_candidate_flag_only_for_high_similarity_non_merges(self) -> None:
        similar_blocked = decide(
            view(make_job(extra={"internal_job_id": 111})),
            view(make_job(source="lever", source_job_id="2", extra={"internal_job_id": 222})),
        )
        unrelated_company = decide(
            view(make_job(company="Acme Inc")),
            view(make_job(source="lever", source_job_id="2", company="Other Corp")),
        )

        assert similar_blocked.candidate is True
        assert similar_blocked.merged is False
        assert unrelated_company.candidate is False
