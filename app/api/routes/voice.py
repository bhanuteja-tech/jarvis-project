"""ElevenLabs Text-to-Speech API route for high-fidelity voice playback."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default ElevenLabs female voice)


def _clean_text_for_tts(text: str) -> str:
    """Remove markdown artifacts and code snippets before sending to ElevenLabs."""
    if not text:
        return ""
    clean = re.sub(r"```[\s\S]*?```", "", text)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"[#*_\-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:1000]  # Cap at 1000 chars per TTS chunk for latency & quota


@router.post("/api/voice/tts")
async def text_to_speech(request: Request) -> Response:
    """Stream MP3 audio synthesized via ElevenLabs API."""
    settings = getattr(request.app.state, "settings", None) or get_settings()
    api_key = (
        settings.elevenlabs_api_key.get_secret_value().strip()
        or settings.eleven_labs_api_key.get_secret_value().strip()
    )
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail={"code": "no_voice_key", "message": "ElevenLabs API key is not configured"},
        )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    raw_text = str(payload.get("text") or "").strip()
    clean_text = _clean_text_for_tts(raw_text)
    if not clean_text:
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_text", "message": "No speakable text provided"},
        )

    voice_id = str(payload.get("voice_id") or DEFAULT_VOICE_ID).strip()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": clean_text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.warning(
                    "ElevenLabs API error",
                    extra={"status_code": resp.status_code, "body": resp.text[:200]},
                )
                raise HTTPException(
                    status_code=resp.status_code,
                    detail={"code": "elevenlabs_error", "message": resp.text[:200]},
                )
            return Response(content=resp.content, media_type="audio/mpeg")
    except httpx.HTTPError as exc:
        logger.exception("Failed to connect to ElevenLabs API")
        raise HTTPException(
            status_code=502,
            detail={"code": "elevenlabs_connection_error", "message": str(exc)},
        ) from exc
