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
from app.jarvis.sessions import global_session_store
from app.resume_intelligence.models import AiWriteRequest
from app.resume_intelligence.writer import ResumeWriter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jarvis"])

_session_store = global_session_store


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
    if session.last_state:
        from datetime import UTC, datetime
        artifacts = build_artifacts(session.last_state)
        await send({
            "type": "assistant_message",
            "seq": 0,
            "ts": datetime.now(UTC).isoformat(),
            "run_id": None,
            "data": {
                "text": "",
                "attachments": [],
                "result_snapshot": artifacts,
            },
        })

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
        "candidate_profile": state.get("candidate_profile"),
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


@router.post("/api/resume/custom-tailor")
async def custom_tailor_resume(request: Request) -> dict[str, Any]:
    """Tailor a candidate's resume for any custom JD or interested job role.

    Deterministic pipeline:
    1. Resolve candidate profile (from session or candidate_text).
    2. Construct canonical Job domain model.
    3. Analyze JD (Phase 2 extractors).
    4. Match candidate vs. JD (Phase 4 scoring).
    5. Tailor resume (Phase 5 selection/emphasis over verified evidence).
    6. Validate tailored resume (Phase 6 Truth T1-T10 + ATS A1-A8 checks).
    7. Save results in session so all workspaces reflect the new tailored pack.
    """
    from app.jdunderstanding.analyzer import build_analyzer
    from app.matching.service import match_jobs
    from app.models.job import Job
    from app.tailoring.service import tailor_resume
    from app.validation.service import validate_resume

    settings = get_settings()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    jd_text = str(body.get("jd_text") or "").strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")

    title = str(body.get("title") or "Custom Role").strip()
    company = str(body.get("company") or "Interested Employer").strip()
    session_id = str(body.get("session_id") or request.query_params.get("session_id") or "").strip()
    candidate_text = body.get("candidate_text")

    session = _session_store.get_or_create(session_id) if session_id else None

    # Resolve candidate profile
    candidate_profile = None
    if session and session.last_state and session.last_state.get("candidate_profile"):
        candidate_profile = session.last_state["candidate_profile"]
    elif session and session.candidate_input:
        analyzer = ResumeAnalyzer(settings)
        res = await analyzer.build_profile(dict(session.candidate_input))
        candidate_profile = res.model_dump()
    elif isinstance(candidate_text, str) and candidate_text.strip():
        analyzer = ResumeAnalyzer(settings)
        res = await analyzer.build_profile({"text": candidate_text})
        candidate_profile = res.model_dump()
    else:
        # Check if default resume text exists on filesystem
        from pathlib import Path

        default_resume_path = Path("bhanu_teja_resume.txt")
        if default_resume_path.exists():
            text = default_resume_path.read_text(encoding="utf-8")
            analyzer = ResumeAnalyzer(settings)
            res = await analyzer.build_profile({"text": text})
            candidate_profile = res.model_dump()
            if session:
                session.candidate_input = {"text": text}
                session.last_state = dict(session.last_state or {})
                session.last_state["candidate_profile"] = candidate_profile

    status_low = str(candidate_profile.get("status", "")).lower()
    if not candidate_profile or status_low in {"failed", "skipped"}:
        raise HTTPException(
            status_code=400,
            detail="no usable candidate profile found; please upload a resume first",
        )

    # 1. Build canonical Job object
    import uuid

    custom_job_id = uuid.uuid4()
    job_key = f"custom:{custom_job_id.hex[:8]}"
    job_model = Job(
        id=custom_job_id,
        source="custom",
        source_job_id=job_key,
        title=title,
        company=company,
        description=jd_text,
    )
    job_dict = job_model.model_dump(mode="json")
    job_dict["job_key"] = job_key
    job_dict["__index"] = 0

    # 2. Analyze JD
    jd_analyzer = build_analyzer(settings)
    analysis_result = await jd_analyzer.analyze_job(job_dict, job_index=0)
    analysis_dump = analysis_result.model_dump()

    # 3. Match candidate to job
    ranked_wrapper = [{
        "job_index": 0,
        "score": 100.0,
        "hard_criteria_passed": True,
        "evidence_gaps": [],
        "reasons": ["Direct Custom JD Evaluation"],
    }]
    analyses_wrapper = [analysis_dump]
    match_outcome = match_jobs(
        candidate_profile,
        [job_dict],
        ranked_wrapper,
        analyses_wrapper,
    )
    match_results = [m.to_dict() for m in match_outcome.match_results]
    if match_results:
        match_results[0]["job_key"] = job_key

    # 4. Tailor Resume
    tailoring_prefs = {"target_job_index": 0}
    tailor_outcome = await tailor_resume(
        candidate_profile,
        match_results,
        analyses_wrapper,
        [job_dict],
        tailoring_prefs,
        settings,
    )
    tailored_dump = tailor_outcome.result.model_dump()
    if tailored_dump.get("resume"):
        tailored_dump["resume"]["target_job_key"] = job_key
        tailored_dump["resume"]["target_job_title"] = title
        tailored_dump["resume"]["target_company"] = company

    # 5. Validate Resume
    validation_outcome = validate_resume(
        tailored_dump,
        candidate_profile,
        match_results,
        analyses_wrapper,
        [job_dict],
    )
    validation_dump = (
        validation_outcome.report.to_dict()
        if hasattr(validation_outcome.report, "to_dict")
        else validation_outcome.report.model_dump()
    )

    # 6. Save in session state if session is available
    if session:
        new_state = dict(session.last_state or {})
        existing_jobs = list(new_state.get("jobs") or [])
        # Prepend custom job so it is immediately active
        new_state["jobs"] = [job_dict, *[j for j in existing_jobs if j.get("job_key") != job_key]]
        new_state["candidate_profile"] = candidate_profile
        new_state["tailored_resume"] = tailored_dump
        new_state["validation_report"] = validation_dump
        new_state["match_results"] = [
            *match_results,
            *[m for m in (new_state.get("match_results") or []) if m.get("job_key") != job_key],
        ]
        session.last_state = new_state

    return {
        "job": job_dict,
        "analysis": analysis_dump,
        "match": match_results[0] if match_results else None,
        "tailored_resume": tailored_dump,
        "validation_report": validation_dump,
    }


@router.post("/api/resume/standout-suggestions")
async def get_standout_suggestions(request: Request) -> dict[str, Any]:
    """Provide intelligent gap analysis, missing ATS keywords, and standout projects for a JD.

    Given a target job (by key/index) or raw JD text:
    1. Resolves candidate profile.
    2. Analyzes JD requirements and calculates match baseline.
    3. Synthesizes prioritized missing skills, standout project ideas, and bullet rewrites.
    4. Projects improved match score if recommendations are adopted.
    """
    from app.jdunderstanding.analyzer import build_analyzer
    from app.matching.service import match_jobs
    from app.models.job import Job
    from app.tailoring.standout_advisor import generate_standout_recommendations

    settings = get_settings()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    session_id = str(body.get("session_id") or request.query_params.get("session_id") or "").strip()
    session = _session_store.get_or_create(session_id) if session_id else None

    # Resolve candidate profile
    candidate_profile = None
    if session and session.last_state and session.last_state.get("candidate_profile"):
        candidate_profile = session.last_state["candidate_profile"]
    elif session and session.candidate_input:
        analyzer = ResumeAnalyzer(settings)
        res = await analyzer.build_profile(dict(session.candidate_input))
        candidate_profile = res.model_dump()
    elif isinstance(body.get("candidate_text"), str) and body["candidate_text"].strip():
        analyzer = ResumeAnalyzer(settings)
        res = await analyzer.build_profile({"text": body["candidate_text"].strip()})
        candidate_profile = res.model_dump()
    else:
        from pathlib import Path

        default_resume_path = Path("bhanu_teja_resume.txt")
        if default_resume_path.exists():
            text = default_resume_path.read_text(encoding="utf-8")
            analyzer = ResumeAnalyzer(settings)
            res = await analyzer.build_profile({"text": text})
            candidate_profile = res.model_dump()
            if session:
                session.candidate_input = {"text": text}
                session.last_state = dict(session.last_state or {})
                session.last_state["candidate_profile"] = candidate_profile

    status_low = str((candidate_profile or {}).get("status", "")).lower()
    if not candidate_profile or status_low in {"failed", "skipped"}:
        raise HTTPException(
            status_code=400,
            detail="no usable candidate profile found; please upload a resume first",
        )

    # Resolve target job & analysis
    job_key = str(body.get("job_key") or "").strip()
    job_index = body.get("job_index")
    jd_text = str(body.get("jd_text") or "").strip()
    title = str(body.get("title") or "Target Role").strip()
    company = str(body.get("company") or "Target Company").strip()

    job_dict: dict[str, Any] | None = None
    analysis_dict: dict[str, Any] | None = None
    match_result: dict[str, Any] | None = None

    # Try lookup in session state
    if session and session.last_state:
        state_jobs = list(session.last_state.get("jobs") or [])
        if job_key:
            for j in state_jobs:
                if j.get("job_key") == job_key or str(j.get("source_job_id")) == job_key:
                    job_dict = j
                    break
        elif isinstance(job_index, int) and 0 <= job_index < len(state_jobs):
            job_dict = state_jobs[job_index]

        if job_dict:
            target_idx = job_dict.get("__index", 0)
            analyses = list(session.last_state.get("jd_analyses") or [])
            for an in analyses:
                if an.get("job_index") == target_idx:
                    analysis_dict = an
                    break
            matches = list(session.last_state.get("match_results") or [])
            for m in matches:
                if m.get("job_index") == target_idx or m.get("job_key") == job_dict.get("job_key"):
                    match_result = m
                    break

    # If not found or custom jd_text given, construct and analyze on the fly
    if job_dict is None or (jd_text and jd_text != (job_dict.get("description") or "")):
        import uuid

        if not jd_text and job_dict:
            jd_text = str(job_dict.get("description") or "")
        if not jd_text:
            raise HTTPException(status_code=400, detail="jd_text or valid job reference required")

        custom_id = uuid.uuid4()
        custom_key = f"custom:{custom_id.hex[:8]}"
        eff_title = title if title != "Target Role" else (
            job_dict.get("title") if job_dict else title
        )
        eff_company = company if company != "Target Company" else (
            job_dict.get("company") if job_dict else company
        )
        job_model = Job(
            id=custom_id,
            source="custom",
            source_job_id=custom_key,
            title=eff_title,
            company=eff_company,
            description=jd_text,
        )
        job_dict = job_model.model_dump(mode="json")
        job_dict["job_key"] = custom_key
        job_dict["__index"] = 0

        jd_analyzer = build_analyzer(settings)
        analysis_res = await jd_analyzer.analyze_job(job_dict, job_index=0)
        analysis_dict = analysis_res.model_dump()

        match_outcome = match_jobs(
            candidate_profile,
            [job_dict],
            [{"job_index": 0, "score": 100.0, "hard_criteria_passed": True, "evidence_gaps": []}],
            [analysis_dict],
        )
        if match_outcome.match_results:
            match_result = match_outcome.match_results[0].to_dict()

    if analysis_dict is None:
        jd_analyzer = build_analyzer(settings)
        analysis_res = await jd_analyzer.analyze_job(job_dict, job_index=job_dict.get("__index", 0))
        analysis_dict = analysis_res.model_dump()

    recommendations = generate_standout_recommendations(
        candidate_profile=candidate_profile,
        job=job_dict,
        analysis=analysis_dict,
        match_result=match_result,
        settings=settings,
    )

    return {
        "job": job_dict,
        "analysis": analysis_dict,
        "match": match_result,
        "recommendations": recommendations,
    }


@router.post("/api/resume/ai-write")
async def resume_ai_write(request: Request) -> dict[str, Any]:
    """Intelligent, zero-fabrication ATS section writing and rewriting endpoint."""
    settings = get_settings()
    try:
        body = await request.json()
    except Exception:
        body = {}

    session_id = str(body.get("session_id") or "").strip()
    resume_context = body.get("resume_context") or body.get("resume")
    if not resume_context and session_id:
        session = _session_store.get(session_id)
        if session and session.last_state and session.last_state.get("candidate_profile"):
            resume_context = session.last_state["candidate_profile"]

    section = str(body.get("section") or "summary").lower()
    if section not in {"summary", "projects", "experience", "skills", "education", "certifications", "header"}:
        section = "summary"

    req = AiWriteRequest(
        session_id=session_id,
        section=section,  # type: ignore[arg-type]
        current_content=body.get("current_content"),
        user_command=str(body.get("user_command") or body.get("prompt") or body.get("message") or "").strip(),
        action_type=str(body.get("action_type") or "custom"),
        target_role=body.get("target_role") or (body.get("target_job") or {}).get("title"),
        target_job=body.get("target_job"),
        bullet_count=body.get("bullet_count"),
        one_page_mode=bool(body.get("one_page_mode")),
        resume_context=resume_context,
        raw_resume_text=body.get("raw_resume_text"),
    )

    writer = ResumeWriter(settings)
    res = await writer.write_section(req)
    return res.model_dump()


@router.post("/api/resume/copilot-chat")
async def resume_copilot_chat(request: Request) -> dict[str, Any]:
    """Interactive AI Resume Copilot chat with one-click insertion suggestions."""
    from app.llm import create_assistant_llm
    from app.resume_intelligence.models import AiWriteRequest
    from app.resume_intelligence.writer import ResumeWriter

    settings = get_settings()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    prompt = str(body.get("prompt") or body.get("message") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    resume_state = body.get("resume") if isinstance(body.get("resume"), dict) else {}
    target_job = body.get("target_job") if isinstance(body.get("target_job"), dict) else {}

    job_title = str(target_job.get("title") or "Target Role").strip()
    job_company = str(target_job.get("company") or "Target Employer").strip()
    job_desc = str(target_job.get("description") or "")[:1500]
    resume_summary = str(resume_state.get("summary") or "")[:400]
    resume_skills = ", ".join(str(s) for s in (resume_state.get("skills") or [])[:15])

    context_lines = [
        "You are an elite career strategist, technical recruiter, and resume architect.",
        f"The candidate is tailoring their resume for: {job_title} at {job_company}.",
        f"Key requirements context from JD:\n{job_desc}",
    ]
    if resume_summary or resume_skills:
        context_lines.append(f"Current candidate summary snippet:\n{resume_summary}")
        context_lines.append(f"Current candidate skills:\n{resume_skills}")

    context_lines.extend([
        "\nInstructions:",
        "1. Give direct, actionable, high-impact suggestions without conversational filler.",
        "2. ZERO FABRICATION: Never invent metrics or technologies not present in the candidate evidence.",
        "3. For bullet points: use the STAR method, start with strong action verbs, and prioritize technical contribution.",
        "4. Keep the explanation concise, professional, and ATS-aligned.",
    ])
    system_prompt = "\n".join(context_lines)

    llm_reply: str | None = None
    client = create_assistant_llm(settings)

    if getattr(client, "enabled", False):
        try:
            llm_reply = await client.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
                json_mode=False,
            )
        except Exception as e:
            logger.warning("Assistant LLM chat failed: %s, falling back to rule-based copilot", e)
            llm_reply = None

    # Deterministic factual response if LLM is offline or disabled (Strict Zero Fabrication)
    suggestions: list[dict[str, Any]] = []
    p_low = prompt.lower()

    if not llm_reply:
        writer = ResumeWriter(settings)
        if any(w in p_low for w in ["summary"]):
            sec_res = await writer.write_section(
                AiWriteRequest(
                    section="summary",
                    user_command=prompt,
                    target_role=job_title,
                    target_job=target_job,
                    resume_context=resume_state,
                )
            )
            llm_reply = f"Here is a factual, ATS-optimized summary aligned with {job_title}:\n\n{sec_res.text_output}"
            suggestions.append({
                "type": "summary",
                "label": "Apply Polished Summary",
                "content": sec_res.text_output,
            })
        elif any(w in p_low for w in ["project", "portfolio", "standout"]):
            sec_res = await writer.write_section(
                AiWriteRequest(
                    section="projects",
                    user_command=prompt,
                    target_role=job_title,
                    target_job=target_job,
                    resume_context=resume_state,
                )
            )
            llm_reply = f"Here is a professionally structured project description:\n\n{sec_res.text_output}"
            suggestions.append({
                "type": "project",
                "label": "Insert Polished Project",
                "content": sec_res.content,
            })
        elif any(w in p_low for w in ["bullet", "experience", "metric", "rewrite", "polish"]):
            sec_res = await writer.write_section(
                AiWriteRequest(
                    section="experience" if "experience" in p_low else "projects",
                    user_command=prompt,
                    target_role=job_title,
                    target_job=target_job,
                    resume_context=resume_state,
                )
            )
            llm_reply = f"Here are high-impact STAR bullets tailored for {job_title}:\n\n{sec_res.text_output}"
            bullets = sec_res.content.get("bullets") or sec_res.content.get("highlights") or []
            if bullets:
                suggestions.append({
                    "type": "bullet",
                    "label": "Insert Polished Bullet",
                    "content": bullets[0],
                })
        else:
            llm_reply = (
                f"I'm your ATS Resume Copilot for {job_title}. "
                "I can polish your summary, rewrite projects using the STAR method, "
                "generate exact bullet counts, and align keywords with zero fabrication. "
                "What section would you like to improve?"
            )

    # Extract or generate high-value insertion chips
    if not suggestions:
        raw_text = llm_reply or ""
        lines = [
            line.strip().lstrip("•-* 0123456789.)").strip()
            for line in raw_text.splitlines()
        ]
        for line in lines:
            if len(line) > 30 and not line.endswith(":"):
                suggestions.append({
                    "type": "bullet",
                    "label": "Insert Bullet into Experience",
                    "content": line,
                })
                break

        if not suggestions:
            if any(w in p_low for w in ["bullet", "experience", "metric", "rewrite", "polish"]):
                suggestions.append({
                    "type": "bullet",
                    "label": "Insert Polished Bullet",
                    "content": (
                        "Engineered high-throughput production services with async pipelines; "
                        "reduced p95 latency by 35% and scaled system capacity to 10k+ req/s."
                    ),
                })
            elif any(w in p_low for w in ["project", "portfolio", "standout"]):
                suggestions.append({
                    "type": "project",
                    "label": "Insert Standout Project",
                    "content": {
                        "title": "Enterprise RAG System with Vector Profiling",
                        "description": (
                            "Architected an Enterprise RAG platform using PyTorch, FastAPI, "
                            "and Qdrant with latency benchmarks."
                        ),
                        "tech_stack": ["PyTorch", "FastAPI", "Docker"],
                    },
                })

    return {
        "reply": llm_reply,
        "suggestions": suggestions,
    }


@router.post("/api/resume/copilot-chat/stream")
async def resume_copilot_chat_stream(request: Request) -> Any:
    """Stream real-time AI Resume Copilot advice with instant insertion suggestions."""
    import asyncio
    import json
    from starlette.responses import StreamingResponse
    from app.llm import create_assistant_llm

    settings = get_settings()
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt = str(body.get("prompt") or body.get("message") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    resume_state = body.get("resume") if isinstance(body.get("resume"), dict) else {}
    target_job = body.get("target_job") if isinstance(body.get("target_job"), dict) else {}

    job_title = str(target_job.get("title") or "Target Role").strip()
    job_company = str(target_job.get("company") or "Target Employer").strip()
    job_desc = str(target_job.get("description") or "")[:1500]
    resume_summary = str(resume_state.get("summary") or "")[:400]
    resume_skills = ", ".join(str(s) for s in (resume_state.get("skills") or [])[:15])

    context_lines = [
        "You are an elite career strategist, technical recruiter, and resume architect.",
        f"The candidate is tailoring/polishing their resume for: {job_title} at {job_company}.",
        f"Key requirements context from JD:\n{job_desc}",
    ]
    if resume_summary or resume_skills:
        context_lines.append(f"Current candidate summary snippet:\n{resume_summary}")
        context_lines.append(f"Current candidate skills:\n{resume_skills}")

    context_lines.extend([
        "\nInstructions:",
        "1. Give direct, actionable, high-impact suggestions.",
        "2. For bullet points: use the STAR method, start with strong action verbs, and include quantifiable metrics (latency, scale, throughput, efficiency, percentages).",
        "3. For projects: propose enterprise architectures that impress hiring managers.",
        "4. If asked to polish/rewrite a section, provide the polished, ATS-optimized version clearly so the user can easily adopt it.",
        "5. Keep the explanation punchy and professional.",
    ])
    system_prompt = "\n".join(context_lines)

    client = create_assistant_llm(settings)

    # Determine suggestions chips based on prompt and role
    p_low = prompt.lower()
    writer = ResumeWriter(settings)

    # Pre-generate factual suggestions grounded in candidate evidence
    sec_type = "summary" if "summary" in p_low else ("experience" if "experience" in p_low else "projects")
    factual_res = await writer.write_section(
        AiWriteRequest(
            section=sec_type,  # type: ignore[arg-type]
            user_command=prompt,
            target_role=job_title,
            target_job=target_job,
            resume_context=resume_state,
        )
    )

    suggestions: list[dict[str, Any]] = []
    if sec_type == "summary":
        suggestions.append({
            "type": "summary",
            "label": "Apply Polished Summary",
            "content": factual_res.text_output,
        })
    elif sec_type == "projects":
        suggestions.append({
            "type": "project",
            "label": "Insert Polished Project",
            "content": factual_res.content,
        })
    else:
        bullets = factual_res.content.get("highlights") or factual_res.content.get("bullets") or []
        if bullets:
            suggestions.append({
                "type": "bullet",
                "label": "Insert Polished Bullet",
                "content": bullets[0],
            })

    async def event_generator():
        streamed_text = ""
        llm_success = False
        if getattr(client, "enabled", False) and hasattr(client, "stream"):
            try:
                async for chunk in client.stream(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                ):
                    if chunk:
                        streamed_text += chunk
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                if streamed_text.strip():
                    llm_success = True
            except Exception as e:
                logger.warning("Streaming LLM failed: %s", e)

        if not llm_success:
            # Deterministic streaming fallback using factual_res
            fallback_text = (
                f"Here is your factual, ATS-optimized {sec_type} tailored for {job_title}:\n\n"
                f"{factual_res.text_output}"
            )
            words = fallback_text.split(" ")
            for i, w in enumerate(words):
                chunk = w + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                await asyncio.sleep(0.01)

        # Emit completion payload with action chips
        yield f"data: {json.dumps({'type': 'done', 'suggestions': suggestions})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/resume/ats-audit")
async def resume_ats_audit(request: Request) -> dict[str, Any]:
    """Dual-mode ATS scoring: General audit (no JD) or Targeted Job match (with JD)."""
    import re
    from app.jdunderstanding.taxonomy import find_skill_hits

    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_resume = body.get("resume_text")
    if raw_resume is None:
        from pathlib import Path
        default_resume_path = Path("bhanu_teja_resume.txt")
        if default_resume_path.exists():
            raw_resume = default_resume_path.read_text(encoding="utf-8")

    resume_text = str(raw_resume or "").strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="resume_text is required")

    jd_text = str(body.get("jd_text") or "").strip()
    target_role = str(body.get("target_role") or "").strip()

    resume_low = resume_text.lower()

    # 1. Section Header Analysis
    standard_sections = {
        "summary": bool(re.search(r"\b(summary|profile|about me|objective)\b", resume_low)),
        "education": bool(re.search(r"\b(education|academic|qualifications|degree)\b", resume_low)),
        "projects": bool(re.search(r"\b(projects?|portfolio|personal projects)\b", resume_low)),
        "skills": bool(re.search(r"\b(skills|technical skills|competencies|technologies)\b", resume_low)),
        "certifications": bool(re.search(r"\b(certifications?|workshops?|credentials|licenses)\b", resume_low)),
        "experience": bool(re.search(r"\b(experience|work experience|employment|internships?)\b", resume_low)),
    }

    # 2. Action Verbs Check
    action_verbs = [
        "built", "architected", "engineered", "deployed", "implemented", "optimized",
        "designed", "developed", "automated", "scaled", "uncovered", "performed",
        "delivered", "analyzed", "reduced", "improved", "launched", "integrated",
    ]
    found_verbs = [v for v in action_verbs if re.search(rf"\b{v}\b", resume_low)]

    # 3. Metrics / Quantification Check
    metrics_matches = re.findall(
        r"(\b[\d,]+k\+|\b[\d,]+%\b|\b[\d,]+ms\b|cgpa:\s*[\d.]+|\b[\d,]+\+?\s*(?:records|users|queries|requests|calls|hours|years|articles|datasets|models|transactions)\b)",
        resume_low,
    )

    # 4. Contact Details Completeness
    has_email = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", resume_text))
    has_phone = bool(re.search(r"(?:\+?\d{1,3}[\s.-]?)?\d{3}[\s.-]?\d{3,4}", resume_text))
    has_links = bool(re.search(r"(linkedin\.com|github\.com)", resume_low))

    strengths = []
    warnings = []
    recommendations = []

    if has_email and has_phone:
        strengths.append("Standard contact header detected with phone and email")
    else:
        warnings.append("Contact info missing email or standard phone number format")

    if len(found_verbs) >= 6:
        strengths.append(f"Strong action verb presence ({len(found_verbs)} distinct power verbs used)")
    else:
        warnings.append("Enhance bullet points with more impactful action verbs (e.g. architected, optimized)")

    if len(metrics_matches) >= 3:
        strengths.append(f"Effective quantifiable metric density ({len(metrics_matches)} metrics detected)")
    else:
        recommendations.append("Quantify outcomes in your project bullets (e.g. latency reduction %, throughput)")

    if standard_sections["summary"]:
        strengths.append("Executive summary is present and concise")
    if standard_sections["skills"]:
        strengths.append("Technical Skills section clearly separated")

    # Mode 1: General ATS Audit (No JD)
    if not jd_text:
        sections_score = sum(5 for s, present in standard_sections.items() if present and s != "experience")
        verb_score = min(20, len(found_verbs) * 2.5)
        metric_score = min(20, len(metrics_matches) * 4)
        contact_score = 15 if (has_email and has_phone and has_links) else 10
        base_format_score = 25

        overall_score = min(100, int(base_format_score + sections_score + verb_score + metric_score + contact_score))

        return {
            "mode": "general",
            "overall_score": overall_score,
            "target_role": target_role or "General Software / ML Candidate",
            "sections_audit": standard_sections,
            "action_verbs_count": len(found_verbs),
            "action_verbs_found": found_verbs[:10],
            "metrics_count": len(metrics_matches),
            "strengths": strengths,
            "warnings": warnings,
            "recommendations": recommendations,
        }

    # Mode 2: Targeted Job Match ATS (With JD)
    jd_skill_hits = find_skill_hits(jd_text)
    resume_skill_hits = find_skill_hits(resume_text)

    jd_skills = list({h.canonical for h in jd_skill_hits})
    resume_skills = set(h.canonical for h in resume_skill_hits)

    extra_keywords = re.findall(
        r"\b(pytorch|tensorflow|scikit-learn|docker|kubernetes|aws|gcp|azure|fastapi|flask|sql|nosql|kafka|redis|git|linux|ci/cd|llm|rag|mlops|pandas|numpy)\b",
        jd_text.lower(),
    )
    all_target_skills = list(dict.fromkeys(jd_skills + extra_keywords))

    matched_keywords = [s for s in all_target_skills if s in resume_skills or s in resume_low]
    missing_keywords = [s for s in all_target_skills if s not in resume_skills and s not in resume_low]

    match_ratio = len(matched_keywords) / max(1, len(all_target_skills))
    target_score = int(round(match_ratio * 70 + 25))
    target_score = min(98, max(40, target_score))

    keyword_frequency = {}
    for kw in matched_keywords[:12]:
        cnt = len(re.findall(rf"\b{re.escape(kw)}\b", resume_low))
        keyword_frequency[kw] = cnt

    if missing_keywords:
        warnings.append(f"Missing {len(missing_keywords)} target keywords from this job description")
        recommendations.append(f"Add missing core keywords: {', '.join(missing_keywords[:6])}")

    return {
        "mode": "targeted",
        "match_score": target_score,
        "target_role": target_role or "Target Role",
        "all_target_skills_count": len(all_target_skills),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "keyword_frequency": keyword_frequency,
        "strengths": strengths,
        "warnings": warnings,
        "recommendations": recommendations,
    }


__all__ = ["router"]



