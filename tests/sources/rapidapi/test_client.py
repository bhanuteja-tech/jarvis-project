"""Unit tests for RapidApiClient."""

from __future__ import annotations

import httpx
import pytest

from app.config.settings import Settings
from app.sources.errors import (
    SourceConfigurationError,
    SourceRateLimitError,
    SourceTimeoutError,
)
from app.sources.rapidapi.client import RapidApiClient


@pytest.mark.asyncio
async def test_client_missing_key_raises_configuration_error():
    settings = Settings(rapidapi_api_key="", x_rapidapi_key="")
    with pytest.raises(SourceConfigurationError) as exc_info:
        RapidApiClient(settings)
    assert "RAPIDAPI_API_KEY is empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_client_successful_search():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-RapidAPI-Key"] == "test-key"
        assert request.headers["X-RapidAPI-Host"] == "jsearch.p.rapidapi.com"
        mock_data = [{"job_id": "job123", "job_title": "ML Engineer"}]
        return httpx.Response(200, json={"status": "OK", "data": mock_data})

    transport = httpx.MockTransport(handler)
    settings = Settings(rapidapi_api_key="test-key", rapidapi_host="jsearch.p.rapidapi.com")

    async with RapidApiClient(settings, transport=transport) as client:
        res = await client.search({"query": "ML Engineer"})
        assert res["status"] == "OK"
        assert len(res["data"]) == 1
        assert res["data"][0]["job_id"] == "job123"


@pytest.mark.asyncio
async def test_client_rate_limit_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "5"})

    transport = httpx.MockTransport(handler)
    settings = Settings(rapidapi_api_key="test-key")

    async with RapidApiClient(settings, transport=transport) as client:
        with pytest.raises(SourceRateLimitError) as exc:
            await client.search({"query": "ML Engineer"})
        assert exc.value.retry_after_seconds == 5.0


@pytest.mark.asyncio
async def test_client_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    settings = Settings(rapidapi_api_key="test-key")

    async with RapidApiClient(settings, transport=transport) as client:
        with pytest.raises(SourceTimeoutError):
            await client.search({"query": "ML Engineer"})
