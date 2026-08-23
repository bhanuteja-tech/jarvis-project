"""GoogleJobsAdapter behavior: identity, canonical mapping, pagination guards.

All HTTP is MockTransport; no network occurs. Includes the approved
correction guard: time_period is NEVER sent to engine=google_jobs.
"""

from __future__ import annotations

import pytest

from app.models.job import Job
from app.sources.base import FetchResult
from app.sources.errors import SourceValidationError
from app.sources.searchapi.jobs_adapter import (
    GoogleJobsAdapter,
    derive_fallback_id,
    extract_htidocid,
)
from tests.support import (
    ScriptedRouter,
    json_response,
    load_searchapi_fixture,
    make_searchapi_client,
)

HTIDOCID = "2_EkUK_X1ZOKUz-CAAAAAA=="


def make_adapter(
    router: ScriptedRouter,
    *,
    max_pages: int | None = None,
    **client_overrides,
) -> GoogleJobsAdapter:
    client = make_searchapi_client(router, **client_overrides)
    kwargs = {"max_pages": max_pages} if max_pages is not None else {}
    return GoogleJobsAdapter(client, **kwargs)


def preferences(**extra_params) -> dict:
    params = {"q": "machine learning intern", **extra_params}
    return {"searchapi": {"google_jobs": params}}


async def collect(adapter: GoogleJobsAdapter) -> FetchResult:
    return await adapter.fetch_jobs(preferences())


class TestIdentityStrategy:
    def test_htidocid_extracted_from_sharing_link(self) -> None:
        link = "https://www.google.com/search?ibp=htl;jobs&htidocid=2_EkUK_X1ZOKUz-CAAAAAA%3D%3D"
        assert extract_htidocid(link) == HTIDOCID

    def test_missing_sharing_link_yields_no_htidocid(self) -> None:
        assert extract_htidocid(None) is None
        assert extract_htidocid("https://www.google.com/search?q=x") is None

    async def test_primary_identity_is_upstream_derived(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        (first, _, _) = result.jobs
        assert first.source_job_id == f"gj:{HTIDOCID}"
        assert first.extra["identity_source"] == "htidocid"

    async def test_fallback_identity_is_deterministic_content_hash(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        (_, second, _) = result.jobs
        assert second.source_job_id.startswith("derived:")
        assert second.extra["identity_source"] == "derived"

        expected = derive_fallback_id(
            company_name="Fallback Co",
            title="Data Engineer (Fallback Identity)",
            location="Austin, TX",
        )
        assert second.source_job_id == expected

        # Same inputs -> same id again (no clock/randomness involved).
        assert (
            derive_fallback_id(
                company_name="Fallback Co",
                title="Data Engineer (Fallback Identity)",
                location="Austin, TX",
            )
            == expected
        )


def _two_page_router() -> ScriptedRouter:
    """jobs_page carries a next-page token, so a terminator page follows."""
    return ScriptedRouter(
        json_response(load_searchapi_fixture("jobs_page.json")),
        json_response(load_searchapi_fixture("jobs_next_page.json")),
    )


class TestCanonicalMapping:
    async def test_documented_fields_map_onto_canonical_job(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        result = await collect(adapter)

        assert isinstance(result, FetchResult)
        (job, _, _) = result.jobs

        assert job.source == "searchapi"
        assert job.title == "Applied AI Engineer"
        assert job.company == "Example AI Corp"
        assert job.location == "New York, NY"
        assert job.description is not None and job.description.startswith("About the role")
        # job_highlights are provenance only — never promoted.
        assert job.requirements is None
        assert job.responsibilities is None
        # detected_extensions.schedule -> employment_type.
        assert job.employment_type == "Full-time"
        # No structured salary exists upstream.
        assert job.salary is None
        # No trustworthy absolute timestamps exist upstream.
        assert job.source_created_at is None
        assert job.source_updated_at is None
        assert job.apply_url == (
            "https://careers.example.com/job/applied-ai-engineer"
            "?utm_campaign=google_jobs_apply&utm_source=google_jobs_apply&utm_medium=organic"
        )
        assert job.job_url is not None and "htidocid" in job.job_url
        assert job.apply_url != job.job_url

    async def test_extra_preserves_provenance_without_inventing_timestamps(self) -> None:
        router = _two_page_router()
        adapter = make_adapter(router)

        (job, _, _) = (await collect(adapter)).jobs

        assert job.extra["engine"] == "google_jobs"
        assert job.extra["query"] == "machine learning intern"
        assert job.extra["position"] == 1
        assert job.extra["via"] == "via Example Careers"
        assert job.extra["posted_at_display"] == "1 day ago"
        assert job.extra["detected_extensions"]["health_insurance"] is True
        assert job.extra["job_highlights"][0]["title"] == "Qualifications"
        assert job.extra["apply_links"][0]["source"] == "Example Careers"
        # Nothing pretends relative text became a timestamp.
        assert "created_at" not in job.extra

    async def test_missing_optional_fields_remain_none(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_missing_optional.json")))
        adapter = make_adapter(router)

        (job,) = (await collect(adapter)).jobs

        assert isinstance(job, Job)
        assert job.company is None
        assert job.location is None
        assert job.description is None
        assert job.employment_type is None
        assert job.salary is None
        assert job.job_url is None
        assert job.source_created_at is None
        assert all(job.extra[key] is None for key in ("via", "posted_at_display"))


class TestPagination:
    async def test_token_pagination_stops_when_token_empty(self) -> None:
        router = ScriptedRouter(
            json_response(load_searchapi_fixture("jobs_page.json")),
            json_response(load_searchapi_fixture("jobs_next_page.json")),
        )
        adapter = make_adapter(router)

        result = await collect(adapter)

        ids = [job.source_job_id for job in result.jobs]
        assert len(ids) == len(set(ids))  # duplicates suppressed
        assert len(result.jobs) == 3
        assert result.raw_count == 4
        dupes = [w for w in result.warnings if w.code == "duplicate_skipped"]
        assert len(dupes) == 1
        assert router.call_count == 2  # empty token ended traversal

    async def test_repeated_next_page_token_stops_with_warning(self) -> None:
        page = load_searchapi_fixture("jobs_page.json")  # always TOKEN_PAGE_TWO
        router = ScriptedRouter(json_response(page), json_response(page))
        adapter = make_adapter(router)

        result = await collect(adapter)

        codes = [w.code for w in result.warnings]
        assert "repeated_next_page_token" in codes
        assert router.call_count == 2

    async def test_max_pages_guard_stops_infinite_tokens(self) -> None:
        page = load_searchapi_fixture("jobs_page.json")
        router = ScriptedRouter(*[json_response(page)] * 10)
        adapter = make_adapter(router, max_pages=1)

        result = await collect(adapter)

        assert router.call_count == 1
        codes = [w.code for w in result.warnings]
        assert "max_pages_reached" in codes


class TestPartialDataPolicy:
    async def test_empty_result_set_is_success(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_empty.json")))
        adapter = make_adapter(router)

        result = await collect(adapter)

        assert result.jobs == ()
        assert result.raw_count == 0
        assert not result.errors

    async def test_invalid_item_skipped_but_sibling_survives(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_bad_item.json")))
        adapter = make_adapter(router)

        result = await collect(adapter)

        assert [job.title for job in result.jobs] == ["Valid Sibling Result"]
        failed = [w for w in result.warnings if w.code == "normalization_failed"]
        assert len(failed) == 1

    async def test_structurally_wrong_payload_raises_validation_error(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("malformed_response.json")))
        adapter = make_adapter(router)

        with pytest.raises(SourceValidationError):
            await collect(adapter)


class TestApprovedCorrectionGuards:
    async def test_time_period_is_never_sent_to_google_jobs(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_empty.json")))
        adapter = make_adapter(router)

        await collect_with(router, adapter, time_period="last_30_minutes")

        request = router.last_request
        assert request is not None
        assert "time_period" not in request.url.params

    async def test_time_period_request_emits_warning_and_is_dropped(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_empty.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs(preferences(time_period="last_30_minutes"))

        ignored = [w for w in result.warnings if w.code == "unsupported_parameters_ignored"]
        assert len(ignored) == 1
        assert "time_period" in ignored[0].message

    async def test_unknown_parameters_are_also_dropped_with_warning(self) -> None:
        router = ScriptedRouter(json_response(load_searchapi_fixture("jobs_empty.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs(preferences(num=100))

        message = next(
            w.message for w in result.warnings if w.code == "unsupported_parameters_ignored"
        )
        assert "num" in message

    async def test_no_query_requested_warns_and_makes_no_calls(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs({"searchapi": {"google_jobs": {"gl": "us"}}})

        assert result.jobs == ()
        assert result.warnings[0].code == "no_query_requested"
        assert router.call_count == 0


async def collect_with(
    router: ScriptedRouter, adapter: GoogleJobsAdapter, **extra_params
) -> FetchResult:
    return await adapter.fetch_jobs(preferences(**extra_params))
