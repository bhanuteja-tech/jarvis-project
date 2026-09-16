"""Unit tests for standout advisor recommendations engine."""

from __future__ import annotations

from app.config.settings import Settings
from app.tailoring.standout_advisor import generate_standout_recommendations


def test_standout_advisor_generates_projects_and_skills() -> None:
    settings = Settings()

    # Candidate profile with basic Python & SQL skills
    candidate_profile = {
        "status": "success",
        "profile": {
            "skills": {
                "taxonomy": {
                    "programming_languages": [{"name": "Python"}, {"name": "SQL"}],
                }
            },
            "experience": {
                "roles": [
                    {
                        "title": "Software Engineer",
                        "employer": "Tech Corp",
                        "highlights": ["Maintained backend microservices using Python."],
                    }
                ]
            },
        },
    }

    # Job asking for PyTorch, Docker, MLflow, RAG
    job = {
        "title": "Senior Machine Learning Engineer",
        "company": "AI Innovations",
        "description": (
            "We are seeking an experienced ML Engineer in Bengaluru. "
            "You will build Enterprise RAG pipelines and distributed training architectures. "
            "Required skills: PyTorch, Docker, MLflow, Vector Databases. "
            "Responsibilities: Architect scalable inference services and optimize latency."
        ),
    }

    analysis = {
        "skills_required": [
            {"name": "PyTorch"},
            {"name": "Docker"},
            {"name": "MLflow"},
        ],
        "skills_preferred": [
            {"name": "Ray"},
            {"name": "vLLM"},
        ],
        "responsibilities": [
            "Architect scalable inference services and optimize latency.",
            "Deploy multi-modal RAG systems with high throughput.",
        ],
    }

    match_result = {
        "score": 48.0,
        "matched_skills": ["python"],
        "missing_requirements": ["pytorch", "docker", "mlflow"],
    }

    res = generate_standout_recommendations(
        candidate_profile=candidate_profile,
        job=job,
        analysis=analysis,
        match_result=match_result,
        settings=settings,
    )

    assert res["current_score"] == 48.0
    assert res["projected_score"] > res["current_score"]
    assert res["projected_score"] >= 80.0

    # Verify missing skills
    missing_names = [s["name"] for s in res["missing_skills"]]
    assert "PyTorch" in missing_names
    assert "Docker" in missing_names
    assert "MLflow" in missing_names
    assert "Ray" in missing_names

    # Verify standout projects
    assert len(res["standout_projects"]) >= 2
    top_proj = res["standout_projects"][0]
    assert "title" in top_proj
    assert "tagline" in top_proj
    assert "tech_stack" in top_proj
    assert "resume_bullet" in top_proj
    assert "why_it_stands_out" in top_proj
    assert len(top_proj["tech_stack"]) > 0

    # Verify bullet suggestions
    assert len(res["bullet_suggestions"]) > 0
    assert "suggested_bullet" in res["bullet_suggestions"][0]
