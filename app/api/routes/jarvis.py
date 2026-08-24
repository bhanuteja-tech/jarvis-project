"""Jarvis interface routes: WebSocket session + REST conveniences."""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.websockets import WebSocketState

from app.candidate.analyzer import ResumeAnalyzer
from app.config.settings import get_settings
from app.jarvis.document_parser import DocumentParseError, extract, metadata
from app.jarvis.orchestrator import JarvisOrchestrator
from app.jarvis.sessions import InMemorySessionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jarvis"])

_session_store = InMemorySessionStore()


class _BoundedRunStore:
    """Deterministic FIFO retention over completed runs (oldest evicted).

    In-memory only; the most recent ``max_entries`` runs are retained. There
    is no persistence layer by design — restarts forget everything.
    """

    def __init__(self, max_entries: int) -> None:
        self._max = max(1, int(max_entries))
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def put(self, run_id: str, payload: dict[str, Any]) -> None:
        self._data.pop(run_id, None)  # re-insertions move to newest
        self._data[run_id] = payload
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self._data.get(run_id)

    def __contains__(self, run_id: object) -> bool:
        return run_id in self._data

    def __len__(self) -> int:
        return len(self._data)


def _bounded_capacity() -> int:
    return int(getattr(get_settings(), "jarvis_max_stored_runs", 100))


_runs: _BoundedRunStore | None = None
_run_artifacts: _BoundedRunStore | None = None


def _run_store() -> _BoundedRunStore:
    global _runs
    if _runs is None:
        _runs = _BoundedRunStore(_bounded_capacity())
    return _runs


def _artifact_store() -> _BoundedRunStore:
    global _run_artifacts
    if _run_artifacts is None:
        _run_artifacts = _BoundedRunStore(_bounded_capacity())
    return _run_artifacts


def reset_stores_for_tests() -> None:
    global _runs, _run_artifacts
    _runs = None
    _run_artifacts = None


def _get_orchestrator() -> JarvisOrchestrator:
    return JarvisOrchestrator(get_settings(), session_store=_session_store)


def _origin_allowed(websocket: WebSocket) -> bool:
    """Same-origin gate for the browser handshake.

    - Absent Origin (non-browser clients / tests): allowed.
    - Origin host equal to the Host header: allowed.
    - localhost/127.0.0.1 development origins: allowed.
    - Anything else must appear in settings.jarvis_ws_allow_origins.
    """
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    origin_host = (urlsplit(origin).hostname or "").lower()
    if not origin_host:
        return False
    host_header = (websocket.headers.get("host") or "").split(":")[0].lower()
    if origin_host == host_header:
        return True
    if origin_host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return True
    extra = getattr(settings, "jarvis_ws_allow_origins", "") or ""
    allowed = {entry.strip().lower() for entry in extra.split(",") if entry.strip()}
    return origin_host in allowed


@router.websocket("/ws/jarvis")
async def ws_jarvis(websocket: WebSocket) -> None:
    if not _origin_allowed(websocket):
        # Reject cross-origin handshakes before joining a session.
        await websocket.accept()
        await websocket.close(code=1008)
        logger.warning(
            "ws handshake rejected: cross-origin",
            extra={"source": "jarvis"},
        )
        return

    await websocket.accept()
    session = _session_store.get_or_create(websocket.query_params.get("session_id"))
    orchestrator = _get_orchestrator()

    async def send(envelope: dict[str, Any]) -> None:
        await websocket.send_json(envelope)
        if (
            envelope.get("type") == "completed"
            and session.last_state is not None
            and websocket.client_state == WebSocketState.CONNECTED
        ):
            run_id = envelope.get("run_id")
            if run_id:
                state = session.last_state
                _run_store().put(run_id, {
                    "session_id": session.session_id,
                    "jobs_count": len(state.get("jobs") or []),
                    "matches": len(state.get("match_results") or []),
                    "tailored_target_index": tailored_target_index(state),
                    "validation_status": validation_status(state),
                })
                _artifact_store().put(run_id, build_artifacts(state))

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


def build_artifacts(state: dict[str, Any]) -> dict[str, Any]:
    """PII-free workspace projection with stable job identities."""
    jobs = []
    for index, job in enumerate(state.get("jobs") or []):
        if not isinstance(job, dict):
            continue
        job_key = job.get("id") or (
            f"{job.get('source')}:{job.get('source_job_id')}"
            if job.get("source") and job.get("source_job_id")
            else f"pos:{index}"
        )
        jobs.append({
            "__index": index,
            "job_key": job_key,
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "employment_type": job.get("employment_type"),
            "job_url": job.get("job_url"),
        })
    match_results = [
        {**match, "job_key": jobs[match["job_index"]]["job_key"]}
        if isinstance(match, dict)
        and isinstance(match.get("job_index"), int)
        and 0 <= match["job_index"] < len(jobs)
        else match
        for match in (state.get("match_results") or [])
        if isinstance(match, dict)
    ]
    return {
        "jobs": jobs,
        "match_results": match_results,
        "tailored_resume": state.get("tailored_resume"),
        "validation_report": state.get("validation_report"),
    }


_STATUS_TO_HTTP = {
    "unsupported_format": 415,
    "file_too_large": 413,
    "empty_file": 400,
    "no_extractable_text": 422,
    "invalid_document": 422,
}


def _document_error(exc: DocumentParseError) -> HTTPException:
    status = _STATUS_TO_HTTP.get(exc.code, 422)
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


async def _analyze_text(text: str | None) -> dict[str, Any]:
    analyzer = ResumeAnalyzer(get_settings())
    result = await analyzer.build_profile({"text": text} if isinstance(text, str) else None)
    status_str = str(getattr(result.status, "value", result.status)).lower()
    if status_str == "failed" and result.reason in {
        "empty_resume",
        "invalid_candidate_input",
    }:
        raise HTTPException(status_code=400, detail=result.reason)
    if status_str == "failed":
        raise HTTPException(status_code=422, detail=result.reason)
    dump = result.model_dump()
    # PII quarantine: REST responses strip quarantined values.
    profile = dump.get("profile") or {}
    contact = profile.get("contact") or {}
    contact.update({"emails": [], "phones": [], "links": []})
    return dump


@router.post("/api/resume/parse")
async def parse_resume(request: Request) -> dict[str, Any]:
    """Parse a resume from an uploaded document (multipart) or raw text (JSON).

    Multipart ``file`` goes through the document-extraction layer
    (PDF/DOCX/TXT/MD -> normalized text). JSON ``{"text": ...}`` remains
    fully backward compatible and bypasses extraction.
    """
    settings = get_settings()
    extraction_meta: dict[str, Any] | None = None
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, StarletteUploadFile):
            raise HTTPException(
                status_code=400,
                detail={"code": "empty_file", "message": "no file was provided"},
            )
        data = await upload.read()
        try:
            extracted = extract(
                data=data,
                filename=upload.filename,
                max_bytes=settings.max_resume_upload_bytes,
            )
        except DocumentParseError as exc:
            raise _document_error(exc) from None
        finally:
            await upload.close()
        text: str | None = extracted.text
        extraction_meta = metadata(extracted)
    else:
        raw_body: Any = None
        try:
            raw_body = await request.json()
        except Exception:  # noqa: BLE001 - malformed/empty body falls through
            raw_body = None
        candidate = raw_body.get("text") if isinstance(raw_body, dict) else None
        text = candidate if isinstance(candidate, str) else None

    dump = await _analyze_text(text)
    if extraction_meta is not None:
        dump["extraction"] = extraction_meta
    return dump


def tailored_target_index(state: dict[str, Any]) -> int | None:
    tailored = state.get("tailored_resume") or {}
    resume = tailored.get("resume") or {}
    return resume.get("target_job_index")


def validation_status(state: dict[str, Any]) -> str | None:
    report = state.get("validation_report") or {}
    return report.get("overall_status")


def _authorize_run(run_id: str, session_id: str) -> dict[str, Any]:
    """Session-scoped access to a stored run.

    Isolation contract between anonymous in-memory sessions (NOT auth):
    the caller must present the session_id that created the run. Unknown
    runs 404; known runs owned by another session are rejected with 403
    (existence is not leaked across sessions).
    """
    record = _run_store().get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown run id")
    if not session_id or record.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="run belongs to another session")
    return record


@router.get("/api/runs/{run_id}/result")
async def run_result(
    run_id: str,
    session_id: Annotated[str, Query()] = "",
) -> dict[str, Any]:
    record = dict(_authorize_run(run_id, session_id))
    # Minimal projection: counts + statuses only — never artifacts.
    return {
        "run_id": run_id,
        "jobs_count": record.get("jobs_count"),
        "matches": record.get("matches"),
        "tailored_target_index": record.get("tailored_target_index"),
        "validation_status": record.get("validation_status"),
    }


@router.get("/api/runs/{run_id}/artifacts")
async def run_artifacts(
    run_id: str,
    session_id: Annotated[str, Query()] = "",
) -> dict[str, Any]:
    """Safe structured artifacts for the owning session's workspace."""
    _authorize_run(run_id, session_id)
    artifacts = _artifact_store().get(run_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail="unknown run id")
    return artifacts


__all__ = ["router"]
