"""Shared httpx.MockTransport builders for LLM provider tests.

No test in tests/llm touches a real network endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx


def openai_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def chat_completion_response(content: str, *, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(status_code, text=content)
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
    )


def sse_lines(deltas: list[str]) -> str:
    frames = [
        "data: " + json.dumps({"choices": [{"delta": {"content": d}}]})
        for d in deltas
    ]
    frames.append("data: [DONE]")
    return "\n\n".join(frames) + "\n\n"


def ollama_chat_response(content: str, *, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(status_code, json={"error": content})
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content},
                                    "done": True})


def ollama_tags(models: list[str], *, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(status_code, json={})
    return httpx.Response(
        200,
        json={"models": [{"name": name} for name in models]},
    )


def gemini_generate_response(content: str, *, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(status_code, json={"error": content})
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": content}]}}]},
    )


def gemini_stream_response(deltas: list[str]) -> str:
    """Gemini streaming NDJSON format."""
    lines = []
    for delta in deltas:
        lines.append(json.dumps({"candidates": [{"content": {"parts": [{"text": delta}]}}]}))
    return "\n".join(lines) + "\n"


def anthropic_message_response(content: str, *, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(status_code, json={"error": content})
    return httpx.Response(
        200,
        json={"content": [{"type": "text", "text": content}], "stop_reason": "end_turn"},
    )


def anthropic_stream_response(deltas: list[str]) -> str:
    """Anthropic SSE streaming format."""
    lines = []
    for delta in deltas:
        lines.append("event: content_block_delta")
        payload = json.dumps(
            {"type": "content_block_delta", "delta": {"text": delta}}
        )
        lines.append(f"data: {payload}")
        lines.append("")  # Empty line after each event
    lines.append("event: message_stop")
    lines.append("data: {\"type\": \"message_stop\"}")
    lines.append("")
    return "\n".join(lines)
