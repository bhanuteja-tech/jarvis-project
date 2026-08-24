"""Anthropic Claude vendor adapter: native Messages API.

Wire format (Anthropic Messages API):
- POST /v1/messages
- POST /v1/messages (streaming with accept: text/event-stream)
- Request: {model, max_tokens, messages[{role,content}], system}
- Response: {content[{type,text}], stop_reason}
- Streaming: Server-Sent Events with event: message_delta/content_block_delta

Authentication: x-api-key header (SecretStr never logged).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.settings import Settings
from app.llm.base import (
    AuthenticationFailedError,
    InvalidModelError,
    InvalidResponseError,
    LLMTimeoutError,
    ProviderHTTPError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.llm.resilience import RetryPolicy, execute_with_retry

_DEFAULT_BASE_URL = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
_USER_AGENT = "jarvis-assistant/0.1"


class AnthropicClient:
    enabled = True

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = (
            settings.anthropic_base_url.strip().rstrip("/") or _DEFAULT_BASE_URL
        )
        self._api_key = settings.anthropic_api_key.get_secret_value().strip()
        self._transport = transport
        self._retry_policy = retry_policy or RetryPolicy()
        # Use provider-specific model if configured, otherwise generic setting
        self.model_name = settings.anthropic_model.strip() or settings.jarvis_llm_model.strip()

    def _headers(self, stream: bool = False) -> dict[str, str]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if stream:
            headers["accept"] = "text/event-stream"
        return headers

    def _payload(self, *, system_prompt: str, user_prompt: str, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "max_tokens": self._settings.jarvis_llm_max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
            "system": system_prompt,
        }

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 401 or status_code == 403:
            raise AuthenticationFailedError("Anthropic rejected the API key")
        if status_code == 404:
            raise InvalidModelError("model or endpoint not found on Anthropic")
        if status_code == 429:
            raise RateLimitedError("Anthropic rate limit reached")
        if 500 <= status_code <= 599:
            raise ProviderHTTPError(f"Anthropic server error ({status_code})")
        raise ProviderHTTPError(f"unexpected Anthropic status ({status_code})")

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        if not self._api_key:
            raise AuthenticationFailedError("ANTHROPIC_API_KEY is not configured")

        async def _do_generate() -> str:
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.jarvis_llm_timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/v1/messages",
                        headers=self._headers(stream=False),
                        json=self._payload(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            stream=False,
                        ),
                    )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("Anthropic did not respond in time") from exc
            except httpx.ConnectError as exc:
                raise ProviderUnavailableError("Anthropic endpoint is unreachable") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError("Anthropic connection failed") from exc

            if response.status_code != 200:
                self._raise_for_status(response.status_code)

            try:
                data = response.json()
                # Anthropic response format: content[0].text for text blocks
                content = data["content"][0]["text"]
            except Exception as exc:  # noqa: BLE001 - shape drift is typed
                raise InvalidResponseError("unreadable response from Anthropic") from exc
            if not isinstance(content, str):
                raise InvalidResponseError("response content was not text")
            return content

        return await execute_with_retry(
            _do_generate,
            policy=self._retry_policy,
            context={"provider": "anthropic", "operation": "generate"},
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        if not self._api_key:
            raise AuthenticationFailedError("ANTHROPIC_API_KEY is not configured")

        try:
            client = httpx.AsyncClient(
                timeout=self._settings.jarvis_llm_timeout_seconds,
                transport=self._transport,
            )
            request = client.build_request(
                "POST",
                f"{self._base_url}/v1/messages",
                headers=self._headers(stream=True),
                json=self._payload(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    stream=True,
                ),
            )
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Anthropic did not respond in time") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("Anthropic endpoint is unreachable") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Anthropic connection failed") from exc

        try:
            if response.status_code != 200:
                await response.aread()
                await response.aclose()
                self._raise_for_status(response.status_code)

            # Anthropic streaming uses Server-Sent Events
            async for line in response.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_text = line[len("data:"):].strip()
                if not data_text:
                    continue
                try:
                    chunk = json.loads(data_text)
                    # Look for content_block_delta events with text deltas
                    if chunk.get("type") == "content_block_delta":
                        delta = chunk.get("delta", {}).get("text")
                        if isinstance(delta, str) and delta:
                            yield delta
                except Exception:  # noqa: BLE001 - ignore keep-alive/shape noise
                    continue
        finally:
            await response.aclose()
            await client.aclose()

    async def health(self) -> dict[str, Any]:
        """Reachability check via simple model info call."""
        if not self._api_key:
            return {"reachable": False, "model_available": False, "auth_failed": True}

        try:
            async with httpx.AsyncClient(
                timeout=max(2.0, min(5.0, self._settings.jarvis_llm_timeout_seconds)),
                transport=self._transport,
            ) as client:
                # Use a minimal request to check connectivity
                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._headers(stream=False),
                    json={
                        "model": self.model_name,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        except (httpx.TimeoutException, httpx.HTTPError):
            return {"reachable": False, "model_available": False}

        if response.status_code in (401, 403):
            return {"reachable": True, "model_available": False, "auth_failed": True}
        if response.status_code == 400:
            # Model might be valid but request malformed - treat as reachable
            return {"reachable": True, "model_available": True}
        if response.status_code != 200:
            return {"reachable": True, "model_available": False}

        return {"reachable": True, "model_available": True}


__all__ = ["AnthropicClient"]
