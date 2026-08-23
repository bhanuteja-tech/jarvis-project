"""Normalization, pagination, and error behavior of LeverAdapter.

Verifies the canonical ``Job`` mapping against the verified public Postings
API contract — including offset pagination guards and the explicit rejection
of Data-API-shaped envelopes. All HTTP is MockTransport; no network occurs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.base import FetchResult
from app.sources.errors import SourceConfigurationError, SourceValidationError
from app.sources.lever.adapter import LeverAdapter
from app.sources.lever.registry import FileSiteRegistry
from tests.support import (
    SITE,
    ScriptedRouter,
    json_response,
    load_lever_fixture,
    make_lever_client,
)


def registry_from(tmp_path: Path, mapping: dict[str, str]) -> FileSiteRegistry:
    registry_file = tmp_path / "lever_sites.json"
    registry_file.write_text(json.dumps(mapping), encoding="utf-8")
    return FileSiteRegistry(registry_file)


def make_adapter(
    router: ScriptedRouter,
    registry=None,
    *,
    max_pages: int | None = None,
    **client_overrides,
) -> LeverAdapter:
    client = make_lever_client(router, **client_overrides)
    kwargs = {"max_pages": max_pages} if max_pages is not None else {}
    return LeverAdapter(client, registry=registry, **kwargs)


async def fetch_single_site(router: ScriptedRouter, adapter: LeverAdapter) -> FetchResult:
    return await adapter.fetch_site(SITE)


class TestCanonicalMapping:
    async def test_documented_fields_map_onto_canonical_job(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_page.json")))
        adapter = make_adapter(router, registry=registry_from(tmp_path, {SITE: "Example Corp"}))

        result = await fetch_single_site(router, adapter)

        assert isinstance(result, FetchResult)
        assert len(result.jobs) == 2
        assert result.raw_count == 2
        job = result.jobs[0]

        assert job.source == "lever"
        assert job.source_job_id == "5ac21346-8e0c-4494-8e7a-3eb92ff77901"
        assert job.title == "Senior Platform Engineer"
        assert job.company == "Example Corp"
        assert job.location == "Arlington, TX"
        assert job.employment_type == "Regular Full Time (Salary)"
        assert job.description is not None and job.description.startswith("<p>")
        # Deliberately never heuristically derived from `lists`.
        assert job.requirements is None
        assert job.responsibilities is None
        assert job.job_url == (
            "https://jobs.lever.co/examplecorp/5ac21346-8e0c-4494-8e7a-3eb92ff77901"
        )
        assert job.apply_url == (job.job_url + "/apply")
        assert job.apply_url != job.job_url
        # createdAt epoch-ms -> UTC (observed-but-undocumented field).
        assert job.source_created_at == datetime(2019, 3, 21, 16, 33, 55, 299000, tzinfo=UTC)
        # The public Postings API has no updated-at field.
        assert job.source_updated_at is None

    async def test_salary_range_maps_onto_salary_value_object(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_page.json")))
        adapter = make_adapter(router)

        (job, _) = (await fetch_single_site(router, adapter)).jobs

        assert job.salary is not None
        assert job.salary.min_amount == Decimal("120000.0")
        assert job.salary.max_amount == Decimal("160000.0")
        assert job.salary.currency == "USD"
        assert job.salary.period == "yearly"

    async def test_extra_preserves_provenance_without_inventing_fields(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_page.json")))
        adapter = make_adapter(router)

        (job, second) = (await fetch_single_site(router, adapter)).jobs

        assert job.extra["description_plain"].startswith("We are hiring")
        assert job.extra["team"] == "Professional Services"
        assert job.extra["department"] == "Customer Success"
        assert job.extra["workplace_type"] == "hybrid"
        assert job.extra["country"] == "US"
        assert job.extra["all_locations"] == ["Arlington, TX"]
        assert [entry["text"] for entry in job.extra["lists"]] == ["Requirements", "Benefits"]
        assert job.extra["salary_description_plain"] == "Base salary band for the role."

        assert second.extra["team"] is None
        assert second.extra["workplace_type"] is None
        assert second.extra["country"] is None
        assert second.extra["lists"] is None


class TestPagination:
    async def test_pages_are_collected_in_order_until_short_page(self) -> None:
        router = ScriptedRouter(
            json_response(load_lever_fixture("postings_multi_page_1.json")),
            json_response(load_lever_fixture("postings_multi_page_2.json")),
            json_response(load_lever_fixture("postings_multi_page_final_short.json")),
        )
        adapter = make_adapter(router, lever_page_size=2)

        result = await fetch_single_site(router, adapter)

        ids = [job.source_job_id[-1] for job in result.jobs]
        assert ids == ["1", "2", "3", "4", "5"]
        assert result.raw_count == 5
        assert router.call_count == 3  # short page terminated the loop

    async def test_empty_page_terminates_cleanly(self) -> None:
        router = ScriptedRouter(
            json_response(load_lever_fixture("postings_multi_page_1.json")),
            json_response(load_lever_fixture("postings_empty.json")),
        )
        adapter = make_adapter(router, lever_page_size=2)

        result = await fetch_single_site(router, adapter)

        assert len(result.jobs) == 2
        assert router.call_count == 2

    async def test_duplicate_ids_across_pages_are_suppressed_with_warning(self) -> None:
        router = ScriptedRouter(
            json_response(load_lever_fixture("postings_multi_page_1.json")),
            json_response(load_lever_fixture("postings_duplicate.json")),
            json_response(load_lever_fixture("postings_multi_page_final_short.json")),
        )
        adapter = make_adapter(router, lever_page_size=2)

        result = await fetch_single_site(router, adapter)

        collected = [job.source_job_id for job in result.jobs]
        assert len(collected) == len(set(collected))  # no duplicates collected
        dupes = [w for w in result.warnings if w.code == "duplicate_skipped"]
        assert len(dupes) == 1
        assert "bbbbbbbb-0000-0000-0000-000000000002" in dupes[0].message

    async def test_max_pages_guard_stops_infinite_feeds(self) -> None:
        full_page = load_lever_fixture("postings_multi_page_1.json")  # len == limit
        router = ScriptedRouter(*[json_response(full_page)] * 10)
        adapter = make_adapter(router, lever_page_size=2, max_pages=2)

        result = await fetch_single_site(router, adapter)

        assert router.call_count == 2  # hard ceiling respected
        codes = [w.code for w in result.warnings]
        assert "max_pages_reached" in codes


class TestPartialDataPolicy:
    async def test_empty_board_yields_no_jobs_and_no_errors(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_empty.json")))
        adapter = make_adapter(router)

        result = await fetch_single_site(router, adapter)

        assert result.jobs == ()
        assert result.raw_count == 0
        assert result.warnings == ()
        assert not result.errors

    async def test_missing_optional_fields_remain_none(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_missing_optional.json")))
        adapter = make_adapter(router)

        result = await fetch_single_site(router, adapter)

        (job,) = result.jobs
        assert job.company is None  # no registry configured
        assert job.location is None
        assert job.description is None
        assert job.employment_type is None
        assert job.salary is None
        assert job.source_created_at is None
        assert job.source_updated_at is None
        assert all(value is None for value in job.extra.values())

    async def test_invalid_items_skipped_but_valid_sibling_survives(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_item_invalid.json")))
        adapter = make_adapter(router)

        result = await fetch_single_site(router, adapter)

        assert [job.source_job_id for job in result.jobs] == [
            "eeeeeeee-0000-0000-0000-000000000001"
        ]
        failed = [w for w in result.warnings if w.code == "item_validation_failed"]
        assert len(failed) == 1

    async def test_whitespace_title_fails_canonical_validation(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_whitespace_title.json")))
        adapter = make_adapter(router)

        result = await fetch_single_site(router, adapter)

        assert result.jobs == ()
        codes = [w.code for w in result.warnings]
        assert "normalization_failed" in codes

    async def test_out_of_range_created_at_dropped_with_warning(self) -> None:
        router = ScriptedRouter(
            json_response(load_lever_fixture("postings_overflow_createdat.json"))
        )
        adapter = make_adapter(router)

        result = await fetch_single_site(router, adapter)

        (job,) = result.jobs
        assert job.source_created_at is None
        codes = [w.code for w in result.warnings]
        assert "timestamp_dropped" in codes


class TestErrorSurfacing:
    async def test_data_api_shaped_envelope_is_rejected(self) -> None:
        """{"data": [...], "next": ..., "hasNext": ...} is the /v1 shape."""
        router = ScriptedRouter(
            json_response(load_lever_fixture("postings_malformed_envelope.json"))
        )
        adapter = make_adapter(router)

        with pytest.raises(SourceValidationError):
            await fetch_single_site(router, adapter)

    async def test_invalid_site_raises_configuration_error_without_http(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        with pytest.raises(SourceConfigurationError):
            await adapter.fetch_site("../evil")

        assert router.call_count == 0


class TestMultiSiteOrchestration:
    async def test_failures_do_not_mask_other_sites(self, tmp_path) -> None:
        ok_router = ScriptedRouter(json_response(load_lever_fixture("postings_page.json")))

        class MultiClient:
            source_name = "lever"

            def __init__(self) -> None:
                self._ok = make_lever_client(ok_router)

            @property
            def page_size(self) -> int:
                return self._ok.page_size

            async def fetch_postings_page(self, site: str, *, skip: int = 0, limit=None):
                from app.sources.errors import SourceHTTPError

                if site == "broken-site":
                    raise SourceHTTPError(
                        "site missing",
                        source="lever",
                        endpoint=f"/{site}",
                        status_code=404,
                        retryable=False,
                    )
                return await self._ok.fetch_postings_page(site, skip=skip)

        registry = registry_from(tmp_path, {SITE: "Example Corp"})
        adapter = LeverAdapter(MultiClient(), registry=registry)

        result = await adapter.fetch_jobs({"lever": {"sites": [SITE, "broken-site"]}})

        assert len(result.jobs) == 2
        assert len(result.errors) == 1
        record = result.errors[0].to_record()
        assert record["status_code"] == 404
        assert record["source"] == "lever"

    async def test_no_sites_requested_warns_and_makes_no_calls(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs({})

        assert result.jobs == ()
        assert result.warnings[0].code == "no_sites_requested"
        assert router.call_count == 0

    async def test_duplicate_sites_are_fetched_once(self) -> None:
        router = ScriptedRouter(json_response(load_lever_fixture("postings_empty.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs({"lever": {"sites": [SITE, SITE]}})

        assert router.call_count == 1
        assert result.jobs == ()
