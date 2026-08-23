"""Truth guard + LLM boundary validation."""

from __future__ import annotations

import pytest

from app.tailoring.validator import (
    DisabledTailoringLlmClient,
    TruthinessValidator,
    validate_rewrite,
)

CORPUS = [
    "Built python data pipelines",
    "Managed postgres cluster",
    "Python, SQL",
]


class TestTokenSubsetGuard:
    @pytest.mark.parametrize(
        "text",
        [
            "Built python data pipelines for the platform team",
            "SQL and postgres experience",
            "python pipelines",
        ],
    )
    def test_supported_rewrites_pass(self, text: str) -> None:
        assert TruthinessValidator(CORPUS).is_supported(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Experienced with pytorch and kubernetes",
            "Led a team of 12 engineers",  # invented metric
            "Serving 1M users in production",  # invented scale
            "Senior Machine Learning Engineer",  # title never evidenced
        ],
    )
    def test_fabricated_content_rejected(self, text: str) -> None:
        assert TruthinessValidator(CORPUS).is_supported(text) is False


class TestValidateRewrite:
    def test_accepted_rewrite_returns_new_text(self) -> None:
        accepted, final_text = validate_rewrite(
            TruthinessValidator(CORPUS),
            "Built data pipelines",
            "Built python data pipelines for analytics",
        )

        assert accepted is True
        assert final_text == "Built python data pipelines for analytics"

    def test_rejected_rewrite_keeps_original(self) -> None:
        original = "Built data pipelines"
        accepted, final_text = validate_rewrite(
            TruthinessValidator(CORPUS),
            original,
            "Built pytorch training pipelines at scale",
        )

        assert accepted is False
        assert final_text == original


class TestDisabledClient:
    async def test_disabled_client_raises_if_used_directly(self) -> None:
        client = DisabledTailoringLlmClient()

        with pytest.raises(RuntimeError):
            await client.analyze_structured(system_prompt="x", payload="y", schema={})
