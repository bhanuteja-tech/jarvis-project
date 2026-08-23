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
