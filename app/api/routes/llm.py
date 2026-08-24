"""Safe LLM provider status/test/catalog/preference endpoints.

Responses contain ONLY metadata: names, booleans, model ids, capabilities.
Never: API keys, Authorization values, base URLs carrying credentials, raw
provider responses, prompts, candidate content, or stack traces.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.config.settings import Settings, get_settings
from app.llm import create_assistant_llm
from app.llm.base import safe_status
from app.llm.catalog import (
    PROVIDER_SPECS,
    configured_provider_names,
    is_provider_configured,
    model_for_provider,
)
from app.llm.preferences import PreferenceValidationError, preference_store

router = APIRouter(tags=["llm"])


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _identity(settings: Settings, client: Any) -> tuple[bool, str, str]:
    enabled = bool(getattr(client, "enabled", False))
    if not enabled:
        return False, "", ""
    provider = str(getattr(client, "provider_name", "") or settings.jarvis_llm_provider).lower()
    model = str(getattr(client, "model_name", "") or settings.jarvis_llm_model)
    return True, provider, model


@router.get("/api/llm/status")
async def llm_status(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    client = create_assistant_llm(settings)
    enabled, provider, model = _identity(settings, client)
    if not enabled:
        return safe_status(False, "", "", False)

    try:
        health = await client.health()
        health = health if isinstance(health, dict) else {}
        reachable = bool(health.get("reachable"))
        model_available = bool(health.get("model_available"))
        raw_status = health.get("status")
        health_status = raw_status if isinstance(raw_status, str) else ""
    except Exception:  # noqa: BLE001 - provider errors collapse to unreachable
        reachable = False
        model_available = False
        health_status = "unreachable"

    spec = PROVIDER_SPECS.get(provider)
    capabilities = sorted(spec.capabilities) if spec is not None else []
    payload = safe_status(
        True,
        provider,
        model,
        reachable,
        routing_enabled=bool(settings.jarvis_llm_routing_enabled),
        configured_providers=configured_provider_names(settings),
        capabilities=capabilities,
        model_available=model_available,
        health_status=health_status,
    )
    session_id = request.query_params.get("session_id") or ""
    prefs = preference_store.get(session_id)
    # Safe echo of THIS session's overrides (names/booleans only).
    payload["preferred_provider"] = prefs.preferred_provider
    payload["fallback_providers"] = list(prefs.fallback_providers)
    payload["session_routing_override"] = prefs != type(prefs)() and bool(
        prefs.preferred_provider or prefs.fallback_providers or prefs.routing_enabled
    )
    return payload


@router.post("/api/llm/test")
async def llm_test(request: Request) -> dict[str, Any]:
    payload = await llm_status(request)
    payload["ok"] = bool(payload.get("reachable"))
    return payload


# ---------------------------------------------------------------------------
# Phase 12: saved jobs / home context / traces
# ---------------------------------------------------------------------------

from app.jarvis.observability import trace_recorder  # noqa: E402
from app.jarvis.saved import saved_job_store  # noqa: E402
from app.jarvis.sessions import InMemorySessionStore  # noqa: E402

_session_store = InMemorySessionStore()


def _session(request: Request):
    session_id = request.query_params.get("session_id") or ""
    return session_id, _session_store.get_or_create(session_id) if session_id else None


def _snapshot_from_state(state: dict[str, Any] | None, index: int) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    jobs = state.get("jobs") or []
    if not isinstance(index, int) or not (0 <= index < len(jobs)):
        return None
    job = jobs[index]
    match = next(
        (
            m
            for m in state.get("match_results") or []
            if isinstance(m, dict) and m.get("job_index") == index
        ),
        None,
    )
    snapshot = {**job}
    if isinstance(match, dict):
        snapshot["score"] = match.get("score")
        snapshot["tier"] = match.get("tier")
    return snapshot


@router.post("/api/jobs/saved")
async def save_job(request: Request) -> dict[str, Any]:
    session_id, session = _session(request)
    if not session_id or session is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail={"code": "missing_session",
                                                     "message": "unknown session"})
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    index = body.get("job_index") if isinstance(body, dict) else None

    # Prefer the session's most recent artifacts (fresh snapshot), else the
    # session's last workflow state.
    from app.api.routes.jarvis import _artifact_store, _run_store

    artifacts = None
    for rid in reversed(list(_run_store()._data.keys())):  # noqa: SLF001
        rec = _run_store().get(rid)
        if not rec or rec.get("session_id") != session_id:
            continue
        candidate = _artifact_store().get(rid)
        if candidate and candidate.get("jobs"):
            artifacts = candidate
            break

    snapshot = _snapshot_from_state(artifacts or session.last_state, index)
    if snapshot is None:
        return {"saved": False, "reason": "job_not_found"}
    entry = saved_job_store.add(session_id, snapshot)
    return {"saved": entry is not None, "job": entry}


    if not session_id or session is None:
        return {"jobs": [], "attention": 0}
    jobs = saved_job_store.list(session_id)
    attention = sum(1 for j in jobs if j.get("status") == "saved")
    return {"jobs": jobs, "attention": attention}


@router.delete("/api/jobs/saved/{job_key}")
async def remove_saved(job_key: str, request: Request) -> dict[str, Any]:
    sid, _sess = _session(request)
    removed = saved_job_store.remove(sid or "", job_key)
    return {"removed": removed}


@router.patch("/api/jobs/saved/{job_key}")
async def update_saved_status(job_key: str, request: Request) -> dict[str, Any]:
    sid, _sess = _session(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    status = str(body.get("status", ""))
    ok = saved_job_store.set_status(sid or "", job_key, status)
    return {"updated": ok}


@router.get("/api/home/context")
async def home_context(request: Request) -> dict[str, Any]:
    """Safe greeting facts for the JARVIS home screen."""
    session_id, session = _session(request)
    hour = __import__("datetime").datetime.now(__import__("datetime").UTC).hour
    if hour < 12:
        part = "morning"
    elif hour < 18:
        part = "afternoon"
    else:
        part = "evening"

    state = session.last_state if session else None
    has_resume = bool(state and state.get("candidate_input")) or (
        session is not None and session.candidate_input is not None
    )
    matches = [
        m for m in (state or {}).get("match_results") or [] if isinstance(m, dict)
    ]
    strong = [m for m in matches if m.get("tier") == "strong"]
    saved = saved_job_store.list(session_id or "")
    attention = sum(1 for j in saved if j.get("status") == "saved")

    lines: list[str] = []
    if has_resume:
        lines.append(f"Good {part}. Your resume is ready.")
    if strong:
        lines.append(f"{len(strong)} strong matches found.")
    if attention:
        lines.append(f"{attention} application(s) need attention.")

    return {
        "greeting": f"Good {part}",
        "has_resume": has_resume,
        "strong_matches": len(strong),
        "jobs_found": len((state or {}).get("jobs") or []),
        "saved_count": len(saved),
        "attention": attention,
        "context_lines": lines,
    }


@router.get("/api/traces")
async def recent_traces(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    return {"traces": trace_recorder.recent(limit),
            "counters": trace_recorder.counters()}


@router.get("/api/llm/providers")
async def llm_providers(request: Request) -> dict[str, Any]:
    """Catalog for the AI-engine UI: every known provider with SAFE state.

    ``reachable``/``model_available`` are probed ONLY for the provider that
    would currently serve requests (routing primary or configured default);
    other rows report configuration state without any network I/O.
    """
    settings = _settings(request)
    enabled = bool(settings.jarvis_assistant_llm_enabled)

    active_probe_target = ""
    probe_health: dict[str, Any] | None = None
    if enabled:
        client = create_assistant_llm(settings)
        active_probe_target = str(getattr(client, "provider_name", "") or "").lower()
        if not active_probe_target and settings.jarvis_llm_routing_enabled:
            from app.llm.router import LlmRouter, RouteRequest

            decision = LlmRouter(settings).decide(RouteRequest(task="chat"))
            active_probe_target = decision.provider if decision else ""
        if active_probe_target:
            try:
                import asyncio

                probe_client = create_assistant_llm(settings)
                bound = probe_client
                binder = getattr(probe_client, "bind_task", None)
                if callable(binder):
                    bound = binder("chat")
                health = await asyncio.wait_for(
                    bound.health(),
                    timeout=float(settings.jarvis_llm_health_timeout_seconds),
                )
                probe_health = health if isinstance(health, dict) else {}
            except Exception:  # noqa: BLE001 - collapse to unreachable
                probe_health = {"reachable": False}

    rows: list[dict[str, Any]] = []
    for name in sorted(PROVIDER_SPECS):
        spec = PROVIDER_SPECS[name]
        configured = is_provider_configured(name, settings)
        row: dict[str, Any] = {
            "name": name,
            "configured": configured,
            "capabilities": sorted(spec.capabilities),
        }
        if configured:
            row["model"] = model_for_provider(name, settings)
        else:
            row["model"] = ""
        if enabled and name == active_probe_target and probe_health is not None:
            row["reachable"] = bool(probe_health.get("reachable"))
            row["model_available"] = bool(probe_health.get("model_available"))
            status_value = probe_health.get("status")
            row["health_status"] = (
                status_value if isinstance(status_value, str) else ""
            ) or ("reachable" if row["reachable"] else "unreachable")
        rows.append(row)

    return {"providers": rows}


@router.post("/api/llm/preferences")
async def save_llm_preferences(
    request: Request,
    session_id: Annotated[str, Query()] = "",
) -> dict[str, Any]:
    settings = _settings(request)
    try:
        body: Any = await request.json()
    except Exception:  # noqa: BLE001 - malformed body -> safe 400
        body = None
    try:
        prefs = preference_store.save(
            session_id, settings=settings, payload=body if isinstance(body, dict) else {}
        )
    except PreferenceValidationError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail={"code": exc.code,
                                                     "message": exc.message}) from None
    out = prefs.to_dict()
    out["saved"] = True
    return out


__all__ = ["router"]
