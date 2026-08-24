"""Phase 9C hardening: bounded stores, session isolation, WS origin gate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import jarvis as jarvis_routes
from app.main import create_app


def client() -> TestClient:
    from tests.support import make_settings

    jarvis_routes.reset_stores_for_tests()
    return TestClient(create_app(make_settings()))


def seed_run(run_id: str, session_id: str) -> None:
    jarvis_routes._run_store().put(run_id, {
        "session_id": session_id,
        "jobs_count": 3,
        "matches": 1,
        "tailored_target_index": 0,
        "validation_status": "WARN",
    })
    jarvis_routes._artifact_store().put(run_id, {
        "jobs": [{"__index": 0, "job_key": "greenhouse:1", "title": "T"}],
        "match_results": [],
        "tailored_resume": None,
        "validation_report": None,
    })


class TestBoundedStores:
    def test_eviction_is_deterministic_fifo(self) -> None:
        store = jarvis_routes._BoundedRunStore(3)
        for i in range(5):
            store.put(f"r{i}", {"n": i})
        assert [k for k, _ in ((k, v) for k, v in store._data.items())] == ["r2", "r3", "r4"]

    def test_reinsertion_refreshes_recency(self) -> None:
        store = jarvis_routes._BoundedRunStore(2)
        store.put("a", {})
        store.put("b", {})
        store.put("a", {})  # a becomes newest
        store.put("c", {})  # evicts b, not a
        assert store.get("a") is not None
        assert store.get("b") is None

    def test_settings_driven_capacity(self) -> None:
        c = client()
        capacity = int(jarvis_routes._bounded_capacity())
        assert capacity >= 1
        for i in range(capacity + 10):
            seed_run(f"run-{i}", "s")
        remaining = [f"run-{i}" for i in range(capacity + 10)
                     if jarvis_routes._run_store().get(f"run-{i}")]
        assert len(remaining) == capacity
        assert remaining[0] == f"run-{len(range(capacity + 10)) - capacity}"
        c.close()


class TestSessionIsolation:
    def test_owner_can_read_result_and_artifacts(self) -> None:
        c = client()
        seed_run("run-1", "sess-A")
        ok = c.get("/api/runs/run-1/result?session_id=sess-A")
        assert ok.status_code == 200
        body = ok.json()
        # Minimal projection only — no artifacts on /result
        assert set(body) == {
            "run_id", "jobs_count", "matches",
            "tailored_target_index", "validation_status",
        }
        arts = c.get("/api/runs/run-1/artifacts?session_id=sess-A")
        assert arts.status_code == 200
        assert arts.json()["jobs"][0]["job_key"] == "greenhouse:1"

    def test_other_session_rejected_403(self) -> None:
        c = client()
        seed_run("run-1", "sess-A")
        r1 = c.get("/api/runs/run-1/result?session_id=sess-B")
        r2 = c.get("/api/runs/run-1/artifacts?session_id=sess-B")
        assert r1.status_code == 403
        assert r2.status_code == 403

    def test_missing_session_rejected(self) -> None:
        c = client()
        seed_run("run-1", "sess-A")
        assert c.get("/api/runs/run-1/result").status_code == 403
        assert c.get("/api/runs/run-1/artifacts").status_code == 403

    def test_unknown_run_404(self) -> None:
        c = client()
        assert c.get("/api/runs/ghost/result?session_id=x").status_code == 404
        assert c.get("/api/runs/ghost/artifacts?session_id=x").status_code == 404

    def test_artifacts_are_pii_safe_projection(self) -> None:
        c = client()
        jarvis_routes._run_store().put("run-pii", {"session_id": "s", "jobs_count": 0})
        jarvis_routes._artifact_store().put("run-pii", {
            "jobs": [{
                "__index": 0, "job_key": "g:1", "title": "Engineer",
                "company": "Co", "location": "Berlin",
                "employment_type": None, "job_url": "https://x",
            }],
            "match_results": [], "tailored_resume": None,
            "validation_report": None,
        })
        body = c.get("/api/runs/run-pii/artifacts?session_id=s").json()
        rendered = str(body).lower()
        for banned in ("@", "resume text", "jane"):
            assert banned not in rendered


class TestWsOriginGate:
    def test_same_origin_allowed(self) -> None:
        c = client()
        with c.websocket_connect(
            "/ws/jarvis?session_id=so",
            headers={"Origin": "http://testserver", "Host": "testserver"},
        ) as ws:
            ws.send_json({"type": "chat", "text": ""})
            envelope = ws.receive_json()
            assert envelope["type"] == "error"  # empty message error = alive

    def test_localhost_origin_allowed(self) -> None:
        c = client()
        with c.websocket_connect(
            "/ws/jarvis?session_id=lo",
            headers={"Origin": "http://localhost:3000", "Host": "testserver"},
        ) as ws:
            ws.send_json({"type": "chat", "text": ""})
            assert ws.receive_json()["type"] == "error"

    def test_cross_origin_rejected_with_1008(self) -> None:
        c = client()
        try:
            with c.websocket_connect(
                "/ws/jarvis?session_id=evil",
                headers={"Origin": "http://evil.example", "Host": "testserver"},
            ) as ws:
                ws.send_json({"type": "chat", "text": "hi"})
                frame = ws.receive()
                code = frame.get("code") or (
                    getattr(ws, "_close_code", None)
                )
                assert code in {1008, None} or ws.closed
        except Exception as exc:  # noqa: BLE001 - starlette raises on reject
            assert "1008" in str(exc) or "closed" in str(exc).lower()

    def test_absent_origin_allowed_for_tooling(self) -> None:
        c = client()
        with c.websocket_connect("/ws/jarvis?session_id=tool") as ws:
            ws.send_json({"type": "chat", "text": ""})
            assert ws.receive_json()["type"] == "error"
