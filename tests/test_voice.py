"""Tests for ElevenLabs voice TTS API route."""

from __future__ import annotations

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config.settings import Settings
from app.main import create_app


def test_voice_tts_empty_text():
    settings = Settings(elevenlabs_api_key=SecretStr("test_key"))
    app = create_app(settings)
    client = TestClient(app)

    resp = client.post("/api/voice/tts", json={"text": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "empty_text"


def test_voice_tts_missing_api_key():
    settings = Settings(elevenlabs_api_key=SecretStr(""), eleven_labs_api_key=SecretStr(""))
    app = create_app(settings)
    client = TestClient(app)

    resp = client.post("/api/voice/tts", json={"text": "Hello world"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "no_voice_key"


def test_voice_tts_success():
    settings = Settings(elevenlabs_api_key=SecretStr("test_elevenlabs_key"))
    app = create_app(settings)
    client = TestClient(app)

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            status_code=200,
            content=b"fake_mp3_audio_data",
            headers={"Content-Type": "audio/mpeg"},
        )

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        resp = client.post(
            "/api/voice/tts",
            json={"text": "Hello world, this is ElevenLabs voice."},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content == b"fake_mp3_audio_data"

