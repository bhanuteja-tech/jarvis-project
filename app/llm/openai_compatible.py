"""Shared Chat-Completions wire format (OpenAI / OpenRouter / compatible).

One implementation serves both vendors: they differ only in base URL,
credential header name and a couple of extra headers — all injected by the
vendor adapters. Streaming uses SSE (``data: {...}`` frames terminated by
``data: [DONE]``); only genuine ``delta.content`` strings are yielded.

Cancellation: the underlying httpx stream is closed when the consuming task
is cancelled (async-with + finally), so provider requests stop promptly.
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

_USER_AGENT = "jarvis-assistant/0.1"


class OpenAICompatibleClient:
    """Configurable Chat-Completions client. Never instantiated directly by
    the application — use the vendor adapters or the factory."""

    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str,
        default_base_url: str,
        extra_headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._api_key = api_key
        self._base_url = (
            settings.jarvis_llm_base_url.strip().rstrip("/")
            or default_base_url
        )
        self._extra_headers = extra_headers or {}
        self._transport = transport
        self._retry_policy = retry_policy or RetryPolicy()
        self.enabled = True
        self.model_name = settings.jarvis_llm_model.strip()

    # ---- request scaffolding ---------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            **self._extra_headers,
        }
        return headers

    def _payload(
        self, *, system_prompt: str, user_prompt: str, json_mode: bool, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._settings.jarvis_llm_temperature,
            "max_tokens": self._settings.jarvis_llm_max_tokens,
            "stream": stream,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @staticmethod
    def _raise_for_status(status_code: int, body_snippet: str) -> None:
        if status_code == 401 or status_code == 403:
            raise AuthenticationFailedError("provider rejected the credentials")
        if status_code == 404:
            raise InvalidModelError("model or endpoint not found on provider")
        if status_code == 429:
            raise RateLimitedError("provider rate limit reached")
        if 500 <= status_code <= 599:
            raise ProviderHTTPError(f"provider server error ({status_code})")
        raise ProviderHTTPError(f"unexpected provider status ({status_code})")

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        async def _do_generate() -> str:
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.jarvis_llm_timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=self._payload(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            json_mode=json_mode,
                            stream=False,
                        ),
                    )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("provider did not respond in time") from exc
            except httpx.ConnectError as exc:
                raise ProviderUnavailableError("provider endpoint is unreachable") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError("provider connection failed") from exc

            if response.status_code != 200:
                self._raise_for_status(response.status_code, response.text[:200])

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001 - any shape drift is typed
                raise InvalidResponseError("provider returned an unreadable completion") from exc
            if not isinstance(content, str):
                raise InvalidResponseError("completion content was not text")
            return content

        return await execute_with_retry(
            _do_generate,
            policy=self._retry_policy,
            context={"provider": "openai_compatible", "operation": "generate"},
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        try:
            client = httpx.AsyncClient(
                timeout=self._settings.jarvis_llm_timeout_seconds,
                transport=self._transport,
            )
            request = client.build_request(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    json_mode=False,
                    stream=True,
                ),
            )
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("provider did not respond in time") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("provider endpoint is unreachable") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("provider connection failed") from exc

        try:
            if response.status_code != 200:
                body = (await response.aread()).decode(errors="replace")[:200]
                await response.aclose()
                self._raise_for_status(response.status_code, body)
            async for line in response.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_text = line[len("data:") :].strip()
                if data_text == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_text)
                    delta = chunk["choices"][0]["delta"].get("content")
                except Exception:  # noqa: BLE001 - ignore keep-alive/shape noise
                    continue
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            await response.aclose()
            await client.aclose()

    async def health(self) -> dict[str, Any]:
        """Cheap reachability check via GET {base}/models."""
        try:
            async with httpx.AsyncClient(
                timeout=max(2.0, min(5.0, self._settings.jarvis_llm_timeout_seconds)),
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/models", headers=self._headers()
                )
        except (httpx.TimeoutException, httpx.HTTPError):
            return {"reachable": False, "model_available": False}
        if response.status_code in (401, 403):
            return {"reachable": True, "model_available": False, "auth_failed": True}
        if response.status_code != 200:
            return {"reachable": True, "model_available": False}
        reachable = True
        available = False
        try:
            ids = [entry.get("id") for entry in response.json().get("data", [])]
            available = self.model_name in set(filter(None, ids)) if self.model_name else False
        except Exception:  # noqa: BLE001 - listing shape is informational only
            pass
        return {
            "reachable": reachable,
            "model_available": available or not self.model_name,
        }


__all__ = ["OpenAICompatibleClient"]
