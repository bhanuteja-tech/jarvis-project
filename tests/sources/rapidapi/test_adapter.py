"""Unit tests for RapidApiAdapter and Job normalization."""

from __future__ import annotations

import httpx
import pytest

from app.config.settings import Settings
from app.sources.rapidapi.adapter import (
    RapidApiAdapter,
    build_request_params,
    normalize_job,
)
from app.sources.rapidapi.client import RapidApiClient
from app.sources.rapidapi.schemas import RapidApiJob


def test_build_request_params():
    prefs = {"rapidapi": {"query": "Data Scientist", "num_pages": 2, "remote_jobs_only": True}}
    params = build_request_params(prefs)
    assert params["query"] == "Data Scientist"
    assert params["num_pages"] == "2"
    assert params["remote_jobs_only"] == "true"


def test_normalize_job():
    raw_job = RapidApiJob(
        job_id="12345",
        job_title="Senior Machine Learning Engineer",
        employer_name="TechCorp",
        job_city="Bengaluru",
        job_state="Karnataka",
        job_country="India",
        job_apply_link="https://example.com/apply",
        job_posted_at_timestamp=1700000000,
        job_min_salary=150000,
        job_max_salary=200000,
        job_salary_currency="USD",
        job_salary_period="YEAR",
        job_employment_type="FULLTIME",
        job_description="Great ML position working on LLMs.",
        job_required_skills=["Python", "PyTorch", "Transformers"],
    )

    canonical = normalize_job(raw_job, query="Machine Learning Engineer")
    assert canonical.source == "rapidapi"
    assert canonical.source_job_id == "rapidapi:12345"
    assert canonical.title == "Senior Machine Learning Engineer"
    assert canonical.company == "TechCorp"
    assert canonical.location == "Bengaluru, Karnataka, India"
    assert canonical.apply_url == "https://example.com/apply"
    assert canonical.requirements == "Python, PyTorch, Transformers"
    assert canonical.salary is not None
    assert canonical.salary.min_amount == 150000
    assert canonical.salary.max_amount == 200000
    assert canonical.salary.currency == "USD"
    assert canonical.salary.period == "YEAR"
    assert canonical.source_created_at is not None


@pytest.mark.asyncio
async def test_fetch_jobs_adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "data": [
                    {
                        "job_id": "job_01",
                        "job_title": "AI Research Scientist",
                        "employer_name": "AI Lab",
                        "job_city": "Bengaluru",
                        "job_country": "India",
                        "job_apply_link": "https://lab.ai/jobs/1",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    settings = Settings(rapidapi_api_key="test-key")
    client = RapidApiClient(settings, transport=transport)
    adapter = RapidApiAdapter(client)

    result = await adapter.fetch_jobs({"rapidapi": {"query": "AI Research Scientist"}})
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "AI Research Scientist"
    assert job.company == "AI Lab"
    assert job.source_job_id == "rapidapi:job_01"
    assert result.raw_count == 1
