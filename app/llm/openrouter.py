"""OpenRouter vendor adapter: vendor headers + default base URL only."""

from __future__ import annotations

import httpx

from app.config.settings import Settings
from app.llm.openai_compatible import OpenAICompatibleClient

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient(OpenAICompatibleClient):
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            settings,
            api_key=settings.openrouter_api_key.get_secret_value().strip(),
            default_base_url=_DEFAULT_BASE_URL,
            # Vendor-specific attribution/identifiers stay inside the adapter.
            extra_headers={
                "HTTP-Referer": "https://jarvis.local",
                "X-Title": "Jarvis Career Intelligence Agent",
            },
            transport=transport,
        )


__all__ = ["OpenRouterClient"]
