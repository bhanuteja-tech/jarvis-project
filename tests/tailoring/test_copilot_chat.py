"""Tests for AI resume copilot chat endpoint."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import app


def test_copilot_chat_returns_suggestions() -> None:
    test_client = TestClient(app)
    response = test_client.post(
        "/api/resume/copilot-chat",
        json={
            "prompt": "Suggest 2 high-impact projects for an ML engineer role",
            "resume": {
                "summary": "Experienced Python engineer with backend background.",
                "skills": ["Python", "Docker", "SQL"],
            },
            "target_job": {
                "title": "Senior Machine Learning Engineer",
                "company": "DeepTech AI",
                "description": "Building production RAG and distributed PyTorch pipelines.",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 20
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


def test_copilot_chat_bullet_request() -> None:
    test_client = TestClient(app)
    response = test_client.post(
        "/api/resume/copilot-chat",
        json={
            "prompt": "Rewrite this bullet point to highlight latency metrics",
            "target_job": {
                "title": "Backend ML Engineer",
                "company": "Acme Systems",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["suggestions"]) > 0
    first_sug = data["suggestions"][0]
    assert first_sug["type"] == "bullet"
    assert "content" in first_sug
