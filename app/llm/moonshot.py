"""Moonshot/Kimi vendor adapter: OpenAI-compatible wire format with custom base URL."""

from __future__ import annotations

import httpx

from app.config.settings import Settings
from app.llm.openai_compatible import OpenAICompatibleClient

_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"


class MoonshotClient(OpenAICompatibleClient):
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Use provider-specific base URL if configured, otherwise default
        base_url = settings.moonshot_base_url.strip().rstrip("/") or _DEFAULT_BASE_URL
        # Use provider-specific model if configured, otherwise generic setting
        model = settings.moonshot_model.strip() or settings.jarvis_llm_model.strip()

        super().__init__(
            settings,
            api_key=settings.moonshot_api_key.get_secret_value().strip(),
            default_base_url=base_url,
            extra_headers={},
            transport=transport,
        )
        # Override model_name with provider-specific setting
        if model:
            self.model_name = model


__all__ = ["MoonshotClient"]
