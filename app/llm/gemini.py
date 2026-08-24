"""Google Gemini vendor adapter: native generativelanguage API.

Wire format (Gemini REST API):
- POST /v1beta/models/{model}:generateContent
- POST /v1beta/models/{model}:streamGenerateContent (streaming)
- Request: {contents[{parts[{text}]}], generationConfig{temperature,maxOutputTokens}}
- Response: {candidates[{content:{parts[{text}]}}]}

Authentication: API key as URL query parameter ?key= (SecretStr never logged).
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

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
_USER_AGENT = "jarvis-assistant/0.1"


class GeminiClient:
    enabled = True

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = (
            settings.gemini_base_url.strip().rstrip("/") or _DEFAULT_BASE_URL
        )
        self._api_key = settings.gemini_api_key.get_secret_value().strip()
        self._transport = transport
        self._retry_policy = retry_policy or RetryPolicy()
        # Use provider-specific model if configured, otherwise generic setting
        self.model_name = settings.gemini_model.strip() or settings.jarvis_llm_model.strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }

    def _payload(self, *, system_prompt: str, user_prompt: str, stream: bool) -> dict[str, Any]:
        return {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": self._settings.jarvis_llm_temperature,
                "maxOutputTokens": self._settings.jarvis_llm_max_tokens,
            },
        }

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 401 or status_code == 403:
            raise AuthenticationFailedError("Gemini rejected the API key")
        if status_code == 404:
            raise InvalidModelError("model or endpoint not found on Gemini")
        if status_code == 429:
            raise RateLimitedError("Gemini rate limit reached")
        raise ProviderHTTPError(f"unexpected Gemini status ({status_code})")

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        if not self._api_key:
            raise AuthenticationFailedError("GEMINI_API_KEY is not configured")

        async def _do_generate() -> str:
            endpoint = f"/v1beta/models/{self.model_name}:generateContent"
            url = f"{self._base_url}{endpoint}?key={self._api_key}"

            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.jarvis_llm_timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        url,
                        headers=self._headers(),
                        json=self._payload(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            stream=False,
                        ),
                    )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("Gemini did not respond in time") from exc
            except httpx.ConnectError as exc:
                raise ProviderUnavailableError("Gemini endpoint is unreachable") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError("Gemini connection failed") from exc

            if response.status_code != 200:
                self._raise_for_status(response.status_code)

            try:
                data = response.json()
                content = data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as exc:  # noqa: BLE001 - shape drift is typed
                raise InvalidResponseError("unreadable response from Gemini") from exc
            if not isinstance(content, str):
                raise InvalidResponseError("response content was not text")
            return content

        return await execute_with_retry(
            _do_generate,
            policy=self._retry_policy,
            context={"provider": "gemini", "operation": "generate"},
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        if not self._api_key:
            raise AuthenticationFailedError("GEMINI_API_KEY is not configured")

        endpoint = f"/v1beta/models/{self.model_name}:streamGenerateContent"
        url = f"{self._base_url}{endpoint}?key={self._api_key}"

        try:
            client = httpx.AsyncClient(
                timeout=self._settings.jarvis_llm_timeout_seconds,
                transport=self._transport,
            )
            request = client.build_request(
                "POST",
                url,
                headers=self._headers(),
                json=self._payload(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    stream=True,
                ),
            )
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Gemini did not respond in time") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("Gemini endpoint is unreachable") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Gemini connection failed") from exc

        try:
            if response.status_code != 200:
                await response.aread()
                self._raise_for_status(response.status_code)

            # Gemini streaming response is NDJSON
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    # Gemini streaming format: candidates[0].content.parts[0].text
                    candidate = chunk.get("candidates", [{}])[0]
                    delta = candidate.get("content", {}).get("parts", [{}])[0].get("text")
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

        endpoint = f"/v1beta/models/{self.model_name}"
        url = f"{self._base_url}{endpoint}?key={self._api_key}"

        try:
            async with httpx.AsyncClient(
                timeout=max(2.0, min(5.0, self._settings.jarvis_llm_timeout_seconds)),
                transport=self._transport,
            ) as client:
                response = await client.get(url, headers=self._headers())
        except (httpx.TimeoutException, httpx.HTTPError):
            return {"reachable": False, "model_available": False}

        if response.status_code in (401, 403):
            return {"reachable": True, "model_available": False, "auth_failed": True}
        if response.status_code != 200:
            return {"reachable": True, "model_available": False}

        return {"reachable": True, "model_available": True}


__all__ = ["GeminiClient"]
