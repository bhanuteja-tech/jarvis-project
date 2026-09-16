"""Unit and integration tests for the Resume Intelligence layer and ResumeWriter."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.config.settings import get_settings
from app.main import create_app
from app.resume_intelligence.extractor import build_structured_resume
from app.resume_intelligence.jd_matcher import compare_jd_and_resume
from app.resume_intelligence.models import (
    AiWriteRequest,
    PersonalInfo,
    ProjectEntry,
    SkillCategoryGroup,
    StructuredResume,
)
from app.resume_intelligence.truth_guard import ResumeTruthGuard
from app.resume_intelligence.writer import ResumeWriter, parse_requested_bullet_count


@pytest.fixture
def sample_candidate_resume() -> StructuredResume:
    return StructuredResume(
        personal_info=PersonalInfo(
            name="Lohith Kumar Reddy",
            email="lohith@example.com",
            phone="+91-9876543210",
            location="Bengaluru, India",
        ),
        summary="Software Engineer specializing in Python, SQL, and Oracle database systems.",
        education=[],
        experience=[],
        projects=[
            ProjectEntry(
                title="AI Defective Exhibit Identification System",
                tech_stack=["Python", "Computer Vision", "CNN", "Deep Learning"],
                tech_stack_raw="Python, Computer Vision, CNN, Deep Learning",
                bullets=[
                    "Developed computer vision system using CNNs to identify exhibit defects in real-time.",
                    "Implemented image preprocessing and model evaluation pipelines.",
                ],
            ),
            ProjectEntry(
                title="Oracle EBS Technical Workflows",
                tech_stack=["PL/SQL", "Oracle EBS", "SQL"],
                tech_stack_raw="PL/SQL, Oracle EBS, SQL",
                bullets=[
                    "Engineered robust PL/SQL packages and database triggers for automated enterprise data validation.",
                    "Configured AOL objects including concurrent programs and flex fields.",
                ],
            ),
        ],
        skills=[
            SkillCategoryGroup(
                category="Programming Languages",
                skills=["Python", "SQL", "PL/SQL"],
            ),
            SkillCategoryGroup(
                category="Frameworks & Tools",
                skills=["Computer Vision", "FastAPI", "Docker", "Git"],
            ),
        ],
        certifications=["Oracle Database Certified Associate"],
        raw_text="Lohith Kumar Reddy Python SQL PL/SQL Oracle EBS Computer Vision CNN Deep Learning FastAPI Docker",
    )


@pytest.mark.asyncio
async def test_summary_generation_factual(sample_candidate_resume: StructuredResume) -> None:
    settings = get_settings()
    writer = ResumeWriter(settings)

    req = AiWriteRequest(
        section="summary",
        user_command="Improve my professional summary for an AI Engineer role",
        target_role="AI Engineer",
        target_job={"title": "AI Engineer", "description": "Looking for Python, SQL, and Deep Learning skills"},
        resume_context=sample_candidate_resume.model_dump(),
    )

    resp = await writer.write_section(req)
    assert resp.operation == "rewrite_section"
    assert resp.section == "summary"
    assert "AI Engineer" in resp.text_output
    assert "Python" in resp.text_output or "SQL" in resp.text_output

    # Strict Zero-Fabrication check: must not invent metrics like 42% or 10,000 users
    assert "42%" not in resp.text_output
    assert "10,000" not in resp.text_output
    assert resp.fact_check.supported is True


@pytest.mark.asyncio
async def test_project_rewriting_star_structure(sample_candidate_resume: StructuredResume) -> None:
    settings = get_settings()
    writer = ResumeWriter(settings)

    req = AiWriteRequest(
        section="projects",
        current_content=sample_candidate_resume.projects[0].model_dump(),
        user_command="Make this project ATS friendly using STAR method",
        target_role="Machine Learning Engineer",
        target_job={"title": "Machine Learning Engineer", "description": "Python, CNN, Deep Learning"},
        resume_context=sample_candidate_resume.model_dump(),
    )

    resp = await writer.write_section(req)
    assert resp.section == "projects"
    bullets = resp.content.get("bullets", [])
    assert len(bullets) >= 2

    # Action verb check: every bullet must start with an authoritative verb
    for b in bullets:
        first_word = b.split()[0]
        assert first_word in [
            "Developed",
            "Engineered",
            "Implemented",
            "Architected",
            "Automated",
            "Optimized",
            "Integrated",
            "Deployed",
            "Built",
            "Designed",
            "Configured",
            "Utilized",
            "Leveraged",
            "Created",
            "Spearheaded",
            "Authored",
            "Trained",
            "Collaborated",
            "Led",
            "Managed",
            "Analyzed",
            "Researched",
            "Delivered",
        ]


def test_bullet_count_parsing() -> None:
    assert parse_requested_bullet_count("Give me 3 bullets") == 3
    assert parse_requested_bullet_count("Please write 5 bullet points for this") == 5
    assert parse_requested_bullet_count("Provide 2 points only") == 2
    assert parse_requested_bullet_count("Make it punchy", default=4) == 4


@pytest.mark.asyncio
async def test_exact_bullet_count_enforcement(sample_candidate_resume: StructuredResume) -> None:
    settings = get_settings()
    writer = ResumeWriter(settings)

    for requested in [2, 3, 4]:
        req = AiWriteRequest(
            section="projects",
            current_content=sample_candidate_resume.projects[0].model_dump(),
            user_command=f"Give me {requested} bullets",
            bullet_count=requested,
            target_role="Computer Vision Engineer",
            resume_context=sample_candidate_resume.model_dump(),
        )
        resp = await writer.write_section(req)
        assert len(resp.content.get("bullets", [])) == requested


def test_jd_keyword_comparison_and_no_fabrication_guard(sample_candidate_resume: StructuredResume) -> None:
    target_job = {
        "title": "Senior AI Architect",
        "description": "Requires strong Python, SQL, Docker, AWS, Kubernetes, and Snowflake experience.",
    }

    comparison = compare_jd_and_resume(sample_candidate_resume, target_job)

    # Supported candidate skills present in JD
    assert "Python" in comparison.matched_keywords
    assert "SQL" in comparison.matched_keywords
    assert "Docker" in comparison.matched_keywords

    # Unsupported skills in JD that candidate does NOT have evidence for
    assert "AWS" in comparison.unsupported_keywords or "Kubernetes" in comparison.unsupported_keywords or "Snowflake" in comparison.unsupported_keywords


def test_truth_guard_detects_unverified_metrics(sample_candidate_resume: StructuredResume) -> None:
    guard = ResumeTruthGuard(sample_candidate_resume)

    # 1. Text with verified skills and numbers should pass
    clean_text = "Developed Python and SQL data validation workflows for Oracle EBS."
    res1 = guard.check_text(clean_text)
    assert res1.supported is True
    assert len(res1.flagged_claims) == 0

    # 2. Text with hallucinated metrics must be flagged
    fake_metric_text = "Engineered Python pipeline improving query throughput by 45% with 100,000 daily active users."
    res2 = guard.check_text(fake_metric_text)
    assert res2.supported is False
    assert any("45%" in f for f in res2.flagged_claims)


def test_truth_guard_sanitizer(sample_candidate_resume: StructuredResume) -> None:
    guard = ResumeTruthGuard(sample_candidate_resume)
    raw = "**Developed** Python applications by 35% using `Docker`."
    sanitized = guard.sanitize_output(raw)
    # Bolding and code fences removed
    assert "**" not in sanitized
    assert "`" not in sanitized
    # Invented metric removed or replaced
    assert "35%" not in sanitized


def test_api_ai_write_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    payload = {
        "section": "summary",
        "user_command": "Give me a professional summary for Full Stack Engineer",
        "target_role": "Full Stack Engineer",
        "target_job": {"title": "Full Stack Engineer", "company": "Tech Corp"},
        "resume": {
            "fullName": "Alex Chen",
            "summary": "Full stack engineer with TypeScript and Python experience.",
            "skillGroups": [
                {"category": "Languages", "skills": "TypeScript, Python, SQL"},
            ],
            "projects": [
                {"title": "Cloud Dashboard", "bullets": ["Built responsive frontend and backend REST APIs."]},
            ],
        },
    }

    response = client.post("/api/resume/ai-write", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "rewrite_section"
    assert data["section"] == "summary"
    assert "content" in data
    assert "text_output" in data
    assert "fact_check" in data
    assert data["fact_check"]["supported"] is True
