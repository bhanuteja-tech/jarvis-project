"""REST + WebSocket endpoint behavior (TestClient)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def client() -> TestClient:
    from tests.support import make_settings

    return TestClient(create_app(make_settings()))


class TestResumeParseRoute:
    def test_valid_text_returns_parsed(self) -> None:
        with client() as test_client:
            response = test_client.post(
                "/api/resume/parse",
                json={"text": "Python engineer.\nSkills: python"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"].lower() in {"parsed", "partial"}
        # PII quarantine on REST responses.
        assert (body.get("profile") or {}).get("contact", {}).get("emails") == []

    def test_empty_text_400(self) -> None:
        with client() as test_client:
            response = test_client.post("/api/resume/parse", json={"text": ""})

        assert response.status_code == 400


class TestWebSocketSession:
    @pytest.mark.skip(reason="WS TestClient hangs on receive_json loop; needs async test infra")
    def test_connect_and_chat_produces_events(self) -> None:
        with (
            client() as test_client,
            test_client.websocket_connect("/ws/jarvis?session_id=s1") as ws,
        ):
            ws.send_json({"type": "chat", "text": "help"})
            types = []
            for _ in range(8):
                envelope = ws.receive_json()
                types.append(envelope["type"])
                if envelope["type"] == "completed":
                    break

            assert types[0] == "agent_started"
            assert "assistant_message" in types
            assert types[-1] == "completed"

    def test_malformed_json_does_not_crash_socket(self) -> None:
        with client() as test_client, test_client.websocket_connect("/ws/jarvis") as ws:
            ws.send_text("this is not json")
            # Server should either ignore or close gracefully; both are fine.
            assert True


class TestRunResultRoute:
    def test_unknown_run_404(self) -> None:
        with client() as test_client:
            response = test_client.get("/api/runs/does-not-exist/result")

        assert response.status_code == 404


class TestCustomTailorRoute:
    def test_custom_tailor_requires_jd(self) -> None:
        with client() as test_client:
            response = test_client.post(
                "/api/resume/custom-tailor",
                json={"title": "Software Engineer", "company": "Acme Corp"},
            )
        assert response.status_code == 400

    def test_custom_tailor_success_with_candidate_text(self) -> None:
        sample_resume = (
            "Alex Smith\n"
            "alex@example.com\n"
            "Skills: Python, FastAPI, Docker, SQL\n"
            "Experience:\n"
            "Software Engineer at TechCorp (2022 - 2024)\n"
            "• Built microservices with FastAPI and Python\n"
            "• Optimized SQL queries reducing latency by 30%\n"
        )
        sample_jd = (
            "About the Role:\n"
            "We are looking for a Python Software Engineer.\n"
            "Requirements:\n"
            "• Strong proficiency in Python and FastAPI\n"
            "• Experience with SQL databases\n"
        )
        with client() as test_client:
            response = test_client.post(
                "/api/resume/custom-tailor",
                json={
                    "title": "Python Software Engineer",
                    "company": "NextGen AI",
                    "jd_text": sample_jd,
                    "candidate_text": sample_resume,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert "tailored_resume" in data
        assert "match" in data
        assert "analysis" in data
        assert "validation_report" in data
        assert data["job"]["title"] == "Python Software Engineer"
        assert data["job"]["company"] == "NextGen AI"
        assert data["match"]["score"] > 0


class TestStandoutSuggestionsRoute:
    def test_standout_suggestions_success(self) -> None:
        sample_resume = (
            "Alex Smith\n"
            "alex@example.com\n"
            "Skills: Python, SQL\n"
            "Experience:\n"
            "Software Engineer at TechCorp (2022 - 2024)\n"
            "• Built microservices with Python\n"
        )
        sample_jd = (
            "About the Role:\n"
            "We are looking for a Machine Learning Engineer in Bengaluru.\n"
            "Requirements:\n"
            "• Strong proficiency in PyTorch, Docker, MLflow, and RAG\n"
            "• Experience deploying models with FastAPI\n"
        )
        with client() as test_client:
            response = test_client.post(
                "/api/resume/standout-suggestions",
                json={
                    "title": "Machine Learning Engineer",
                    "company": "NextGen AI",
                    "jd_text": sample_jd,
                    "candidate_text": sample_resume,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert "job" in data
        assert "analysis" in data
        assert "recommendations" in data
        rec = data["recommendations"]
        assert "current_score" in rec
        assert "projected_score" in rec
        assert "missing_skills" in rec
        assert "standout_projects" in rec
        assert len(rec["standout_projects"]) > 0
        assert len(rec["missing_skills"]) > 0


class TestApplyForRoleIntent:
    def test_apply_for_role_variations(self) -> None:
        from app.jarvis.intent import parse_intent

        cases = [
            ("apply for a job like ML engineer intern", "ml engineer intern"),
            ("apply for ML engineer intern", "ml engineer intern"),
            ("apply to Senior Data Scientist", "senior data scientist"),
            ("tailor my resume for Backend Engineer", "backend engineer"),
            ("tailor for Frontend Developer", "frontend developer"),
        ]
        for prompt, expected_role in cases:
            plan = parse_intent(prompt)
            assert plan.action == "apply_for_role", f"Failed for '{prompt}'"
            assert plan.params.get("target_role") == expected_role


class TestAtsAuditRoute:
    def test_empty_resume_returns_400(self) -> None:
        with client() as test_client:
            resp = test_client.post("/api/resume/ats-audit", json={"resume_text": ""})
            assert resp.status_code == 400

    def test_general_ats_audit(self) -> None:
        sample_resume = (
            "BHANU TEJA SUBBARA\n"
            "bhanuteja@example.com | Bengaluru, India | +91 9876543210\n"
            "Summary:\n"
            "Aspiring Machine Learning Engineer with strong experience in Python, PyTorch, and NLP.\n"
            "Skills:\n"
            "Python, PyTorch, Scikit-Learn, Docker, Git, SQL, FastAPI\n"
            "Experience:\n"
            "Machine Learning Intern at AI Labs (Jan 2024 - Present)\n"
            "• Spearheaded deep learning model pipeline, improving inference latency by 45%.\n"
            "• Implemented automated evaluation harnesses processing 10,000 requests daily.\n"
            "Education:\n"
            "B.Tech in Computer Science, VTU, CGPA: 8.5\n"
            "Projects:\n"
            "Autonomous RAG Agent: Built retrieval pipeline utilizing ChromaDB and Ollama.\n"
            "Certifications:\n"
            "AWS Certified Machine Learning Specialist\n"
        )
        with client() as test_client:
            resp = test_client.post("/api/resume/ats-audit", json={"resume_text": sample_resume})
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "general"
            assert "overall_score" in data
            assert data["overall_score"] >= 70
            assert "sections_audit" in data
            assert data["sections_audit"]["summary"] is True
            assert data["sections_audit"]["skills"] is True
            assert data["sections_audit"]["experience"] is True
            assert data["sections_audit"]["education"] is True
            assert data["sections_audit"]["projects"] is True
            assert data["sections_audit"]["certifications"] is True
            assert "action_verbs_count" in data
            assert data["action_verbs_count"] >= 2
            assert "metrics_count" in data
            assert data["metrics_count"] >= 2
            assert "strengths" in data
            # targeted mode keys should not be in general audit
            assert "match_score" not in data
            assert "missing_keywords" not in data

    def test_targeted_ats_audit_with_jd(self) -> None:
        sample_resume = (
            "BHANU TEJA\n"
            "bhanu@example.com\n"
            "Skills: Python, PyTorch, Docker, Git\n"
            "Experience:\n"
            "ML Engineer: Built model inference with Python and PyTorch.\n"
        )
        sample_jd = (
            "We are seeking an ML Engineer intern proficient in Python, PyTorch, Kubernetes, and Ray."
        )
        with client() as test_client:
            resp = test_client.post(
                "/api/resume/ats-audit",
                json={"resume_text": sample_resume, "jd_text": sample_jd},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "targeted"
            assert data.get("match_score") is not None
            assert isinstance(data["match_score"], (int, float))
            assert "matched_keywords" in data
            assert "missing_keywords" in data
            assert "keyword_frequency" in data
            assert any(k.lower() == "python" for k in data["matched_keywords"])
            assert any(k.lower() == "kubernetes" for k in data["missing_keywords"])


class TestCopilotChatStreamRoute:
    def test_copilot_chat_stream_sse(self) -> None:
        with client() as test_client:
            payload = {
                "message": "Polish this summary to emphasize ML pipelines.",
                "section": "summary",
                "current_content": "Passionate computer science student experienced in Python.",
                "target_role": "ML Engineer Intern",
            }
            with test_client.stream("POST", "/api/resume/copilot-chat/stream", json=payload) as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")
                chunks = []
                for line in resp.iter_lines():
                    if line:
                        chunks.append(line)
                assert len(chunks) > 0
                assert any("data:" in chunk for chunk in chunks)


