"""POST /api/resume/parse multipart contract + WS file-upload path."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.main import create_app
from tests.jarvis.doc_fixtures import (
    SAMPLE_RESUME_LINES,
    make_docx,
    make_empty_pdf,
    make_pdf,
)


def client() -> TestClient:
    from tests.support import make_settings

    return TestClient(create_app(make_settings()))


class TestMultipartParse:
    def test_txt_upload(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("resume.txt", b"Python engineer.\nSkills: python")},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"].lower() in {"parsed", "partial"}
        assert body["extraction"]["source_format"] == "txt"
        assert body["profile"]["contact"]["emails"] == []  # PII quarantine holds

    def test_md_upload(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("resume.md", b"# Skills\n- python\n")},
            )
        assert response.status_code == 200
        assert response.json()["extraction"]["source_format"] == "md"

    def test_pdf_upload_reaches_candidate_parser(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={
                    (
                        "file",
                        (
                            "resume.pdf",
                            make_pdf(SAMPLE_RESUME_LINES),
                            "application/pdf",
                        ),
                    )
                },
            )
        assert response.status_code == 200
        body = response.json()
        # Extracted text actually flowed through the frozen Phase-3 parser.
        skill_names = {
            s["name"] for s in body["profile"]["skills"]["items"]
        }
        assert {"python", "sql"} <= skill_names
        assert body["extraction"]["page_count"] == 1
        assert "extraction" in body and "text" not in body["extraction"]

    def test_docx_upload(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("resume.docx", make_docx(["Engineer", "python"]))},
            )
        assert response.status_code == 200
        assert response.json()["extraction"]["source_format"] == "docx"

    def test_scanned_pdf_422_no_extractable_text(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("scanned.pdf", make_empty_pdf())},
            )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "no_extractable_text"

    def test_unsupported_extension_415(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("archive.zip", b"PK\x03\x04zzz")},
            )
        assert response.status_code == 415
        assert response.json()["detail"]["code"] == "unsupported_format"

    def test_empty_file_400(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("resume.txt", b"")},
            )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "empty_file"

    def test_malformed_docx_422(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("broken.docx", b"PK\x03\x04junkjunk")},
            )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_document"

    def test_oversized_file_413(self) -> None:
        settings_payload = b"a" * (31_000)  # > candidate_max_chars path guard
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                files={"file": ("big.txt", settings_payload)},
            )
        # Under max_resume_upload_bytes but over candidate_max_chars after
        # extraction => analyzer hard-fails; must be a typed 413/422, never 500.
        assert response.status_code in {413, 422}

    def test_json_text_path_backward_compatible(self) -> None:
        with client() as c:
            response = c.post(
                "/api/resume/parse",
                json={"text": "Python engineer.\n"},
            )
        assert response.status_code == 200
        assert "extraction" not in response.json()

    def test_json_empty_still_400(self) -> None:
        with client() as c:
            response = c.post("/api/resume/parse", json={"text": ""})
        assert response.status_code == 400


class TestWsFileUploadPath:
    async def test_data_base64_pdf_stores_candidate(self) -> None:
        from app.config.settings import Settings
        from app.jarvis.orchestrator import JarvisOrchestrator
        from app.jarvis.sessions import InMemorySessionStore

        sent: list[dict] = []

        async def send(envelope):
            sent.append(envelope)

        settings = Settings()
        store = InMemorySessionStore()
        session = store.get_or_create("s-pdf")
        orchestrator = JarvisOrchestrator(
            settings,
            session_store=store,
            graph_factory=lambda: None,  # no run started here
        )

        payload = base64.b64encode(make_pdf(SAMPLE_RESUME_LINES)).decode()
        await orchestrator.handle_message(
            session,
            {"type": "resume_upload", "name": "resume.pdf", "data_base64": payload},
            send=send,
        )

        assert session.candidate_input is not None
        completed = [e for e in sent if e["type"] == "tool_completed"]
        assert completed and completed[0]["data"]["skills_found"] >= 2
        errors = [e for e in sent if e["type"] == "error"]
        assert errors == []

    async def test_corrupt_base64_typed_error(self) -> None:
        from app.config.settings import Settings
        from app.jarvis.orchestrator import JarvisOrchestrator
        from app.jarvis.sessions import InMemorySessionStore

        sent: list[dict] = []

        async def send(envelope):
            sent.append(envelope)

        store = InMemorySessionStore()
        session = store.get_or_create("s-bad")
        orchestrator = JarvisOrchestrator(
            Settings(),
            session_store=store,
            graph_factory=lambda: None,
        )

        await orchestrator.handle_message(
            session,
            {"type": "resume_upload", "name": "resume.pdf",
             "data_base64": "!!!not-base64!!!"},
            send=send,
        )

        errors = [e for e in sent if e["type"] == "error"]
        assert errors and errors[0]["data"]["code"] == "invalid_document"
        assert session.candidate_input is None

    async def test_scanned_pdf_ws_error_has_safe_message(self) -> None:
        from app.config.settings import Settings
        from app.jarvis.orchestrator import JarvisOrchestrator
        from app.jarvis.sessions import InMemorySessionStore

        sent: list[dict] = []

        async def send(envelope):
            sent.append(envelope)

        store = InMemorySessionStore()
        session = store.get_or_create("s-scan")
        orchestrator = JarvisOrchestrator(
            Settings(),
            session_store=store,
            graph_factory=lambda: None,
        )

        payload = base64.b64encode(make_empty_pdf()).decode()
        await orchestrator.handle_message(
            session,
            {"type": "resume_upload", "name": "scan.pdf", "data_base64": payload},
            send=send,
        )

        errors = [e for e in sent if e["type"] == "error"]
        assert errors and errors[0]["data"]["code"] == "no_extractable_text"
        rendered = str(errors[0])
        assert "%" not in rendered  # no raw pdf bytes leaked into events
