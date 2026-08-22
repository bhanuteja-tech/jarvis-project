"""LangGraph foundation: single fetch node over the SourceAdapter contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.graph.workflow import build_workflow
from app.models.job import Job
from app.sources.base import FetchResult, SourceWarning
from app.sources.errors import SourceRateLimitError


def make_job(source_job_id: str) -> Job:
    return Job(
        source="greenhouse",
        source_job_id=source_job_id,
        title=f"Role {source_job_id}",
        job_url=f"https://boards.greenhouse.io/examplecorp/jobs/{source_job_id}",
    )


class StubAdapter:
    source_name = "greenhouse"

    def __init__(self, result: FetchResult | Exception) -> None:
        self._result = result
        self.received_preferences: Mapping[str, Any] | None = None

    async def fetch_jobs(self, preferences: Mapping[str, Any]) -> FetchResult:
        self.received_preferences = preferences
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class TestGraphFoundation:
    async def test_jobs_and_discovered_urls_reach_state(self) -> None:
        adapter = StubAdapter(FetchResult(jobs=(make_job("1"), make_job("2"))))
        graph = build_workflow([adapter])

        state = await graph.ainvoke(
            {
                "user_query": "python jobs",
                "search_preferences": {"greenhouse": {"board_tokens": ["examplecorp"]}},
            }
        )

        assert [job["source_job_id"] for job in state["jobs"]] == ["1", "2"]
        assert state["discovered_urls"] == [
            "https://boards.greenhouse.io/examplecorp/jobs/1",
            "https://boards.greenhouse.io/examplecorp/jobs/2",
        ]
        assert state["errors"] == []
        assert adapter.received_preferences == {
            "greenhouse": {"board_tokens": ["examplecorp"]}
        }

    async def test_adapter_failure_becomes_error_record_not_exception(self) -> None:
        failing = StubAdapter(SourceRateLimitError("rate limited", source="greenhouse"))
        succeeding = StubAdapter(FetchResult(jobs=(make_job("9"),)))
        graph = build_workflow([failing, succeeding])

        state = await graph.ainvoke({"search_preferences": {}})

        assert len(state["jobs"]) == 1
        (error,) = state["errors"]
        assert error["kind"] == "SourceRateLimitError"
        assert error["retryable"] is True
        assert error["source"] == "greenhouse"

    async def test_warnings_propagate_into_state(self) -> None:
        adapter = StubAdapter(
            FetchResult(
                jobs=(make_job("3"),),
                warnings=(
                    SourceWarning(
                        source="greenhouse",
                        code="item_validation_failed",
                        message="one item skipped",
                    ),
                ),
            )
        )
        graph = build_workflow([adapter])

        state = await graph.ainvoke({})

        (warning,) = state["warnings"]
        assert warning["code"] == "item_validation_failed"
        assert warning["source"] == "greenhouse"

    async def test_unexpected_exception_recorded_as_unretryable(self) -> None:
        class Exploding(StubAdapter):
            async def fetch_jobs(self, preferences):
                raise RuntimeError("bug in adapter")

        graph = build_workflow([Exploding(FetchResult())])

        state = await graph.ainvoke({})

        (error,) = state["errors"]
        assert error["kind"] == "RuntimeError"
        assert error["retryable"] is False
