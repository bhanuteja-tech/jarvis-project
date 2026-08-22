"""Union-Find clustering, canonical selection, fill-not-overwrite merges."""

from __future__ import annotations

from app.dedup.cluster import dedupe_jobs


def make_job(**overrides):
    base = {
        "source": "greenhouse",
        "source_job_id": "1",
        "title": "Software Engineer",
        "company": "Acme Inc",
        "location": "New York, NY",
        "description": "<p>Build things</p>",
        "requirements": None,
        "responsibilities": None,
        "employment_type": None,
        "salary": None,
        "job_url": f"https://boards.greenhouse.io/acme/jobs/{overrides.get('source_job_id', '1')}",
        "apply_url": None,
        "source_created_at": None,
        "source_updated_at": None,
        "discovered_at": "2026-08-22T10:00:00Z",
        "fetched_at": "2026-08-22T10:00:00Z",
        "extra": {},
    }
    base.update(overrides)
    return base


class TestBasics:
    def test_empty_input_passthrough(self) -> None:
        outcome = dedupe_jobs([])

        assert outcome.jobs == []
        assert outcome.stats["input_records"] == 0

    def test_single_job_passthrough_unchanged(self) -> None:
        job = make_job()

        outcome = dedupe_jobs([job])

        assert len(outcome.jobs) == 1
        assert outcome.jobs[0]["source"] == "greenhouse"
        assert "dedup" not in (outcome.jobs[0].get("extra") or {})

    def test_distinct_companies_stay_separate(self) -> None:
        jobs = [
            make_job(source_job_id=str(i), company=f"Company {i}")
            for i in range(20)
        ]

        outcome = dedupe_jobs(jobs)

        assert len(outcome.jobs) == 20
        # Mandated performance property: no cross-company comparisons at all.
        assert outcome.stats["comparisons"] == 0


class TestClustering:
    def test_transitive_cluster_collapses_to_one(self) -> None:
        a = make_job(source="career_page", source_job_id="url:x", job_url="https://acme.com/jobs/1")
        b = make_job(
            source="greenhouse",
            source_job_id="g1",
            job_url="https://boards.greenhouse.io/acme/jobs/g1",
        )  # shares exact triple keys with c, different url from a
        c = make_job(
            source="lever",
            source_job_id="l1",
            job_url="https://jobs.lever.co/acme/l1",
        )

        outcome = dedupe_jobs([a, b, c])

        assert len(outcome.jobs) == 1
        merged = outcome.jobs[0]
        # Winner is the highest-ranked member (career_page) itself, so it is
        # excluded from the remaining-members list by design.
        assert merged["source"] == "career_page"
        assert merged["extra"]["dedup"]["cluster_size"] == 3
        assert {m["source_job_id"] for m in merged["extra"]["dedup"]["members"]} == {
            "g1",
            "l1",
        }

    def test_r2_merge_across_sources(self) -> None:
        a = make_job(source="greenhouse", source_job_id="1")
        b = make_job(
            source="lever",
            source_job_id="L-7",
            job_url="https://jobs.lever.co/acme/L-7",
        )

        outcome = dedupe_jobs([a, b])

        assert len(outcome.jobs) == 1
        assert outcome.jobs[0]["extra"]["dedup"]["rule"] in {"R2_exact_keys"}

    def test_batch_level_tier0_collapse_keeps_newest(self) -> None:
        older = make_job(fetched_at="2026-08-21T00:00:00Z")
        newer = make_job(fetched_at="2026-08-22T00:00:00Z")

        outcome = dedupe_jobs([older, newer])

        assert len(outcome.jobs) == 1
        assert outcome.jobs[0]["fetched_at"] == "2026-08-22T00:00:00Z"


class TestCanonicalSelection:
    def test_source_rank_beats_completeness(self) -> None:
        greenhouse_minimal = make_job(description=None)
        lever_full = make_job(
            source="lever",
            source_job_id="L-7",
            job_url="https://jobs.lever.co/acme/L-7",
            requirements="5 years",
            employment_type="FULL_TIME",
        )

        outcome = dedupe_jobs([lever_full, greenhouse_minimal])
        winner = outcome.jobs[0]

        # Priority order wins even though the lever record was richer.
        assert winner["source"] == "greenhouse"
        # Fill-not-overwrite: missing winner fields come from members.
        assert winner["employment_type"] == "FULL_TIME"

    def test_fill_never_overwrites_existing_winner_fields(self) -> None:
        a = make_job(title="Software Engineer", description="<p>Greenhouse text</p>")
        b = make_job(
            source="lever",
            source_job_id="L-7",
            job_url="https://jobs.lever.co/acme/L-7",
            title="Totally Different Title Words Here Now",
            description="<p>Lever long-form description that must not win.</p>",
        )

        outcome = dedupe_jobs([a, b])

        winner = outcome.jobs[0]
        assert winner["description"] == "<p>Greenhouse text</p>"
        assert winner["title"] == "Software Engineer"

    def test_earliest_source_created_at_wins(self) -> None:
        earlier = make_job(source_created_at="2026-01-05T00:00:00+00:00")
        later = make_job(
            source="lever",
            source_job_id="L-7",
            job_url="https://jobs.lever.co/acme/L-7",
            source_created_at="2026-03-01T00:00:00+00:00",
        )

        outcome = dedupe_jobs([later, earlier])

        assert (
            outcome.jobs[0]["source_created_at"] == "2026-01-05T00:00:00+00:00"
        )

    def test_provenance_sources_list_includes_every_member(self) -> None:
        a = make_job()
        b = make_job(
            source="lever",
            source_job_id="L-7",
            job_url="https://jobs.lever.co/acme/L-7",
        )

        outcome = dedupe_jobs([a, b])

        sources = outcome.jobs[0]["extra"]["sources"]
        pairs = {(s["source"], s["source_job_id"]) for s in sources}
        assert pairs == {("greenhouse", "1"), ("lever", "L-7")}

    def test_deterministic_ordering_by_winner_original_index(self) -> None:
        first = make_job(source_job_id="a", title="Alpha Role", company="Zeta Corp")
        second = make_job(
            source="lever",
            source_job_id="b",
            company="Beta Corp",
            job_url="https://jobs.lever.co/beta/b",
        )
        duplicate_of_first = make_job(
            source="lever",
            source_job_id="c",
            job_url="https://jobs.lever.co/zeta/a",
            title="Alpha Role",
            company="Zeta Corp",
        )

        outcome = dedupe_jobs([first, second, duplicate_of_first])

        companies = [job["company"] for job in outcome.jobs]
        assert companies == ["Zeta Corp", "Beta Corp"]


class TestPotentialDuplicateWarnings:
    def test_guard_blocked_high_similarity_pair_warns_once(self) -> None:
        a = make_job(
            source_job_id="111", job_url="https://acme.test/jobs/a", extra={"internal_job_id": 111}
        )
        b = make_job(
            source_job_id="222", job_url="https://acme.test/jobs/b", extra={"internal_job_id": 222}
        )

        outcome = dedupe_jobs([a, b])

        codes = [w["code"] for w in outcome.warnings]
        assert codes.count("potential_duplicate") == 1
        assert len(outcome.jobs) == 2

    def test_unrelated_pairs_never_warn(self) -> None:
        jobs = [make_job(company=f"Company {i}") for i in range(30)]

        outcome = dedupe_jobs(jobs)

        assert outcome.warnings == []

    def test_warning_cap_prevents_floods(self) -> None:
        # Same company + same title + distinct URLs + conflicting requisition
        # ids: every pair becomes a candidate that fails V1.
        jobs = [
            make_job(
                source_job_id=str(i),
                job_url=f"https://acme.test/jobs/{i}",
                extra={"internal_job_id": 1000 + i},
            )
            for i in range(120)
        ]

        outcome = dedupe_jobs(jobs)

        potential = [w for w in outcome.warnings if w["code"] == "potential_duplicate"]
        truncated = [
            w for w in outcome.warnings if w["code"] == "potential_duplicate_truncated"
        ]
        assert len(potential) == 50
        assert len(truncated) == 1
