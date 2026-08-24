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
