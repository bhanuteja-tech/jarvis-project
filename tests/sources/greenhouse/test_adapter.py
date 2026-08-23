"""Normalization behavior of GreenhouseAdapter.

Verifies the canonical `Job` mapping, provenance, timestamp handling,
partial-data resilience, and error surfacing — all over MockTransport.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.sources.base import FetchResult
from app.sources.errors import SourceConfigurationError, SourceValidationError
from app.sources.greenhouse.adapter import GreenhouseAdapter
from app.sources.greenhouse.registry import FileBoardRegistry, load_board_registry
from tests.support import (
    TOKEN,
    FakeSleeper,
    ScriptedRouter,
    json_response,
    load_fixture,
    make_client,
)

BOARD_TOKEN_TO_COMPANY = {TOKEN: "Example Corp"}


def make_adapter(
    router: ScriptedRouter,
    registry=None,
    sleeper: FakeSleeper | None = None,
    **client_overrides,
) -> GreenhouseAdapter:
    client = make_client(router, sleeper=sleeper, **client_overrides)
    return GreenhouseAdapter(client, registry=registry)


def registry_from(tmp_path: Path, mapping: dict[str, str]):
    registry_file = tmp_path / "greenhouse_boards.json"
    registry_file.write_text(json.dumps(mapping), encoding="utf-8")
    return FileBoardRegistry(registry_file)


async def fetch_single_board(fixture_name: str, adapter: GreenhouseAdapter) -> FetchResult:
    return await adapter.fetch_board(TOKEN)


class TestCanonicalMapping:
    async def test_documented_fields_map_onto_canonical_job(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_content_true.json")))
        adapter = make_adapter(router, registry=registry_from(tmp_path, BOARD_TOKEN_TO_COMPANY))

        result = await fetch_single_board("list_jobs_content_true.json", adapter)

        assert isinstance(result, FetchResult)
        assert len(result.jobs) == 2
        assert result.raw_count == 2
        job = result.jobs[0]

        assert job.source == "greenhouse"
        assert job.source_job_id == "444001"
        assert job.title == "Senior Platform Engineer"
        assert job.company == "Example Corp"
        assert job.location == "San Francisco, CA"
        assert job.description is not None and job.description.startswith("<p>")
        assert job.requirements is None
        assert job.responsibilities is None
        assert job.employment_type is None
        assert job.salary is None
        assert job.job_url == "https://boards.greenhouse.io/examplecorp/jobs/444001"
        assert job.apply_url == job.job_url
        # -04:00 offset normalized to UTC.
        assert job.source_updated_at == datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC)
        assert job.source_created_at is None
        assert job.extra["internal_job_id"] == 555001
        assert job.extra["requisition_id"] == "101"
        assert job.extra["language"] == "en"
        assert job.extra["is_prospect"] is False

    async def test_prospect_post_is_flagged_not_filtered(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_content_true.json")))
        adapter = make_adapter(router, registry=registry_from(tmp_path, BOARD_TOKEN_TO_COMPANY))

        result = await adapter.fetch_board(TOKEN)

        prospect = result.jobs[1]
        assert prospect.source_job_id == "444002"
        assert prospect.extra["internal_job_id"] is None
        assert prospect.extra["is_prospect"] is True

    async def test_multiple_jobs_preserve_order(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        ids = [job.source_job_id for job in result.jobs]
        assert ids == ["127817", "127818"]

    async def test_offset_timestamps_normalize_to_utc(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        first, second = result.jobs
        assert first.source_updated_at == datetime(2016, 1, 14, 15, 55, 28, tzinfo=UTC)
        assert second.source_updated_at == datetime(2026, 8, 1, 9, 30, 0, tzinfo=UTC)


class TestPartialDataPolicy:
    async def test_empty_board_yields_no_jobs_and_no_errors(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_empty.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        assert result.jobs == ()
        assert result.raw_count == 0
        assert result.warnings == ()
        assert not result.errors

    async def test_missing_optional_fields_remain_none(self) -> None:
        router = ScriptedRouter(
            json_response(load_fixture("list_jobs_missing_optional_fields.json"))
        )
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        (job,) = result.jobs
        assert job.location is None
        assert job.description is None
        assert job.company is None  # no registry configured
        assert job.source_updated_at is None
        assert job.extra["requisition_id"] is None
        assert job.extra["language"] is None

    async def test_naive_timestamp_dropped_with_warning(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_naive_timestamp.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        (job,) = result.jobs
        assert job.source_updated_at is None
        codes = [w.code for w in result.warnings]
        assert "timestamp_dropped" in codes

    async def test_invalid_items_skipped_but_valid_item_survives(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_item_invalid.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        assert [job.source_job_id for job in result.jobs] == ["888002"]
        assert result.raw_count == 3
        failed = [w for w in result.warnings if w.code == "item_validation_failed"]
        assert len(failed) == 2

    async def test_whitespace_only_title_fails_canonical_validation(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_whitespace_title.json")))
        adapter = make_adapter(router)

        result = await adapter.fetch_board(TOKEN)

        assert result.jobs == ()
        codes = [w.code for w in result.warnings]
        assert "normalization_failed" in codes


class TestErrorSurfacing:
    async def test_structurally_wrong_payload_raises_validation_error(self) -> None:
        router = ScriptedRouter(json_response(load_fixture("malformed_response.json")))
        adapter = make_adapter(router)

        with pytest.raises(SourceValidationError):
            await adapter.fetch_board(TOKEN)

    async def test_invalid_token_raises_configuration_error_without_http(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        with pytest.raises(SourceConfigurationError):
            await adapter.fetch_board("../evil")

        assert router.call_count == 0


class TestMultiBoardOrchestration:
    async def test_failures_do_not_mask_other_boards(self, tmp_path) -> None:
        ok_router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))

        class MultiClient:
            source_name = "greenhouse"

            def __init__(self) -> None:
                self._ok = make_client(ok_router)

            async def list_jobs(self, board_token: str):
                if board_token == "broken_board":
                    from app.sources.errors import SourceHTTPError

                    raise SourceHTTPError(
                        "board missing",
                        source="greenhouse",
                        endpoint=f"/{board_token}/jobs",
                        status_code=404,
                        retryable=False,
                    )
                return await self._ok.list_jobs(board_token)

        registry = registry_from(tmp_path, {"good_board": "Good Co"})
        adapter = GreenhouseAdapter(MultiClient(), registry=registry)

        preferences = {
            "greenhouse": {
                "board_tokens": ["good_board", "broken_board"],
            }
        }
        result = await adapter.fetch_jobs(preferences)

        assert len(result.jobs) == 2
        assert len(result.errors) == 1
        record = result.errors[0].to_record()
        assert record["status_code"] == 404
        assert record["source"] == "greenhouse"

    async def test_no_tokens_requested_warns_and_makes_no_calls(self) -> None:
        router = ScriptedRouter()
        adapter = make_adapter(router)

        result = await adapter.fetch_jobs({})

        assert result.jobs == ()
        assert result.warnings[0].code == "no_boards_requested"
        assert router.call_count == 0

    async def test_duplicate_tokens_are_fetched_once(self, tmp_path) -> None:
        fixture = load_fixture("list_jobs_success.json")
        router = ScriptedRouter(json_response(fixture))
        client = make_client(router)
        adapter = GreenhouseAdapter(client, registry=load_board_registry(None))

        result = await adapter.fetch_jobs({"greenhouse": {"board_tokens": [TOKEN, TOKEN]}})

        assert router.call_count == 1
        assert len(result.jobs) == 2


class TestRegistryIntegration:
    async def test_registry_supplies_company_identity(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))
        adapter = make_adapter(router, registry=registry_from(tmp_path, BOARD_TOKEN_TO_COMPANY))

        result = await adapter.fetch_board(TOKEN)

        assert {job.company for job in result.jobs} == {"Example Corp"}

    async def test_unknown_board_has_no_company_value(self, tmp_path) -> None:
        router = ScriptedRouter(json_response(load_fixture("list_jobs_success.json")))
        adapter = make_adapter(router, registry=registry_from(tmp_path, {"other": "Other Co"}))

        result = await adapter.fetch_board(TOKEN)

        assert {job.company for job in result.jobs} == {None}
