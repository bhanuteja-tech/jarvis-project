"""Jarvis interface routes: WebSocket session + REST conveniences."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.candidate.analyzer import ResumeAnalyzer
from app.config.settings import get_settings
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jarvis"])

_session_store = InMemorySessionStore()
_runs: dict[str, dict[str, Any]] = {}


def _get_orchestrator() -> JarvisOrchestrator:
    return JarvisOrchestrator(get_settings(), session_store=_session_store)


@router.websocket("/ws/jarvis")
async def ws_jarvis(websocket: WebSocket) -> None:
    await websocket.accept()
    session = _session_store.get_or_create(websocket.query_params.get("session_id"))
    orchestrator = _get_orchestrator()

    async def send(envelope: dict[str, Any]) -> None:
        await websocket.send_json(envelope)
        if envelope.get("type") == "completed" and session.last_state is not None:
            run_id = envelope.get("run_id")
            if run_id:
                _runs[run_id] = {
                    "session_id": session.session_id,
                    "jobs_count": len(session.last_state.get("jobs") or []),
                    "matches": len(session.last_state.get("match_results") or []),
                    "tailored_target_index": tailored_target_index(
                        session.last_state
                    ),
                    "validation_status": validation_status(session.last_state),
                }

    try:
        while True:
            message = await websocket.receive_json()
            await orchestrator.handle_message(session, message, send=send)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("jarvis ws crashed", extra={"source": "jarvis"})
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@router.post("/api/resume/parse")
async def parse_resume(body: dict[str, Any]) -> dict[str, Any]:
    text = body.get("text") if isinstance(body, dict) else None
    analyzer = ResumeAnalyzer(get_settings())
    result = await analyzer.build_profile(
        {"text": text} if isinstance(text, str) else None
    )
    if result.status.value == "failed" and result.reason in {
        "empty_resume",
        "invalid_candidate_input",
    }:
        raise HTTPException(status_code=400, detail=result.reason)
    if result.status.value == "failed":
        raise HTTPException(status_code=422, detail=result.reason)
    dump = result.model_dump()
    # PII quarantine: REST responses strip quarantined values.
    profile = dump.get("profile") or {}
    contact = profile.get("contact") or {}
    contact.update({"emails": [], "phones": [], "links": []})
    return dump


def tailored_target_index(state: dict[str, Any]) -> int | None:
    tailored = state.get("tailored_resume") or {}
    resume = tailored.get("resume") or {}
    return resume.get("target_job_index")


def validation_status(state: dict[str, Any]) -> str | None:
    report = state.get("validation_report") or {}
    return report.get("overall_status")


@router.get("/api/runs/{run_id}/result")
async def run_result(run_id: str) -> dict[str, Any]:
    snapshot = _runs.get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="unknown run id")
    return snapshot


__all__ = ["router"]
