"""OpenAI vendor adapter: configuration only, wire format is shared."""

from __future__ import annotations

import httpx

from app.config.settings import Settings
from app.llm.openai_compatible import OpenAICompatibleClient

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIClient(OpenAICompatibleClient):
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            settings,
            api_key=settings.openai_api_key.get_secret_value().strip(),
            default_base_url=_DEFAULT_BASE_URL,
            extra_headers={},
            transport=transport,
        )


__all__ = ["OpenAIClient"]
