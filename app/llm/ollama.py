"""Ollama vendor adapter (local, remote, or tunnel-exposed).

Wire format (Ollama HTTP API):
- POST /api/chat   {model, messages, stream, options{temperature,num_predict}}
                   -> non-stream JSON {message:{content}, done}
                   -> streaming NDJSON lines {message:{content}, done}
- GET  /api/tags   -> {models:[{name}]} used for reachability + model check

Nothing is hardcoded: base URL, model and optional bearer token all come
from configuration (JARVIS_LLM_BASE_URL / JARVIS_LLM_MODEL / OLLAMA_API_KEY).
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
    LLMConfigurationError,
    LLMTimeoutError,
    ProviderHTTPError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.llm.ollama_endpoint import (
    ollama_bearer_token,
    redact_secrets,
    resolve_ollama_base_url,
    validate_ollama_base_url,
)
from app.llm.resilience import RetryPolicy, execute_with_retry

_USER_AGENT = "jarvis-assistant/0.1"


class OllamaClient:
    enabled = True

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._settings = settings
        # Empty generic URL uses OLLAMA_BASE_URL, then the loopback default.
        # Production hosts arrive only through configuration (never hardcoded).
        self._base_url = resolve_ollama_base_url(settings)
        self._config_error: LLMConfigurationError | None = None
        try:
            validate_ollama_base_url(
                self._base_url,
                require_https=bool(settings.jarvis_ollama_require_https),
            )
        except LLMConfigurationError as exc:
            self._config_error = exc
        self._transport = transport
        self._retry_policy = retry_policy or RetryPolicy()
        self.model_name = (
            settings.jarvis_llm_model.strip() or settings.ollama_model.strip()
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
        token = ollama_bearer_token(self._settings)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _ensure_ready(self) -> None:
        if self._config_error is not None:
            raise LLMConfigurationError(
                redact_secrets(str(self._config_error), self._settings)
            )

    def _payload(self, *, system_prompt: str, user_prompt: str, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": stream,
            "options": {
                "temperature": self._settings.jarvis_llm_temperature,
                "num_predict": self._settings.jarvis_llm_max_tokens,
            },
        }

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 401 or status_code == 403:
            raise AuthenticationFailedError("tunnel/provider rejected the credentials")
        if status_code == 404:
            raise InvalidModelError("model or endpoint not found on the provider")
        if status_code == 429:
            raise RateLimitedError("provider rate limit reached")
        raise ProviderHTTPError(f"unexpected provider status ({status_code})")

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        self._ensure_ready()

        async def _do_generate() -> str:
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.jarvis_llm_timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/api/chat",
                        headers=self._headers(),
                        json=self._payload(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            stream=False,
                        ),
                    )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("model did not respond in time") from exc
            except httpx.ConnectError as exc:
                raise ProviderUnavailableError("Ollama endpoint is unreachable") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError("Ollama connection failed") from exc

            if response.status_code != 200:
                if response.status_code == 404:
                    # Ollama signals an unknown model with 404 + error body.
                    raise InvalidModelError("model is not available on this Ollama server")
                self._raise_for_status(response.status_code)

            try:
                data = response.json()
                content = data["message"]["content"]
            except Exception as exc:  # noqa: BLE001 - shape drift is typed
                raise InvalidResponseError("unreadable response from Ollama") from exc
            if not isinstance(content, str):
                raise InvalidResponseError("response content was not text")
            return content

        return await execute_with_retry(
            _do_generate,
            policy=self._retry_policy,
            context={"provider": "ollama", "operation": "generate"},
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        self._ensure_ready()
        import contextlib

        try:
            client = httpx.AsyncClient(
                timeout=self._settings.jarvis_llm_timeout_seconds,
                transport=self._transport,
            )
            request = client.build_request(
                "POST",
                f"{self._base_url}/api/chat",
                headers=self._headers(),
                json=self._payload(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    stream=True,
                ),
            )
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("model did not respond in time") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("Ollama endpoint is unreachable") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Ollama connection failed") from exc

        try:
            if response.status_code != 200:
                await response.aread()
                self._raise_for_status(response.status_code)
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(Exception):
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content")
                    if isinstance(delta, str) and delta:
                        yield delta
                    if chunk.get("done"):
                        break
        finally:
            await response.aclose()
            await client.aclose()

    async def health(self) -> dict[str, Any]:
        """Bounded reachability + installed-model check via GET /api/tags.

        Never returns response bodies, Authorization values, or tokens.
        Does not pull or install models.
        """
        if self._config_error is not None:
            return {
                "reachable": False,
                "model_available": False,
                "status": "configuration_error",
            }
        timeout = float(self._settings.jarvis_llm_health_timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/api/tags", headers=self._headers()
                )
        except httpx.TimeoutException:
            return {
                "reachable": False,
                "model_available": False,
                "status": "unreachable",
            }
        except httpx.HTTPError:
            return {
                "reachable": False,
                "model_available": False,
                "status": "unreachable",
            }

        if response.status_code in (401, 403):
            return {
                "reachable": True,
                "model_available": False,
                "auth_failed": True,
                "status": "authentication_failure",
            }
        if 500 <= response.status_code <= 599:
            return {
                "reachable": False,
                "model_available": False,
                "status": "server_unavailable",
            }
        if response.status_code != 200:
            return {
                "reachable": False,
                "model_available": False,
                "status": "server_unavailable",
            }

        model_available = False
        try:
            names = [entry.get("name") for entry in response.json().get("models", [])]
            wanted = self.model_name
            for name in filter(None, names):
                # Ollama lists e.g. "llama3:latest"; config may omit the tag.
                if wanted and (name == wanted or name.split(":")[0] == wanted.split(":")[0]):
                    model_available = True
                    break
        except Exception:  # noqa: BLE001 - informational only
            pass
        return {
            "reachable": True,
            "model_available": model_available,
            "status": "reachable",
        }


__all__ = ["OllamaClient"]
