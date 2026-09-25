"""Main LLM Dynamic Router for JARVIS.

Formalizes dynamic routing between:
1. LOCAL_FAST:  Ollama llama3.2:3b (fast local reasoning, simple/medium commands, low latency)
2. CLOUD_DEEP:   OpenRouter Llama 70B (meta-llama/llama-3.3-70b-instruct) (deep multi-step reasoning,
                 complex recovery, ambiguous synthesis, long context)

Routing Decisions use measurable signals:
- task complexity & multi-step planning
- context length & history depth (> 6 turns)
- recovery required (recovery_count > 0 or failed previous step)
- ambiguity signals from Laya System-1
- tool count and candidate complexity
- local model availability vs cloud quota / key availability
- latency requirements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.settings import Settings, get_settings
from app.llm.catalog import build_provider_client, is_provider_configured, model_for_provider
from app.llm.decision_engine import DecisionResult

logger = logging.getLogger(__name__)


class RouteTier(str, Enum):
    LOCAL_FAST = "LOCAL_FAST"
    CLOUD_DEEP = "CLOUD_DEEP"


@dataclass
class TaskContext:
    """Rich task context inspected by MainLLMRouter to determine execution tier."""

    user_goal: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    recent_actions: list[dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    recovery_count: int = 0
    last_error: str | None = None
    laya_decision: DecisionResult | None = None
    typed_context_size: int = 0
    is_ambiguous: bool = False
    requires_deep_reasoning: bool = False
    force_tier: RouteTier | None = None


@dataclass(frozen=True)
class ModelRouteDecision:
    """Outcome of model routing."""

    tier: RouteTier
    provider: str
    model: str
    reason: str
    fallback_provider: str | None = None
    fallback_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
        }


class MainLLMRouter:
    """Dynamic LLM Router that balances latency, local autonomy, and cloud depth."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def route(self, context: TaskContext) -> ModelRouteDecision:
        """Route task context to LOCAL_FAST or CLOUD_DEEP based on measurable signals."""
        # 1. Check explicit override if set
        if context.force_tier is not None:
            tier = context.force_tier
            reason = "Forced tier override"
            return self._build_decision(tier, reason)

        # 2. Check provider configuration availability
        has_ollama = is_provider_configured("ollama", self._settings)
        has_openrouter = is_provider_configured("openrouter", self._settings)

        # If only one provider is configured, route to that provider
        if has_openrouter and not has_ollama:
            return self._build_decision(RouteTier.CLOUD_DEEP, "Ollama unavailable; using OpenRouter 70B")
        if has_ollama and not has_openrouter:
            return self._build_decision(RouteTier.LOCAL_FAST, "OpenRouter unconfigured; using Ollama 3.2:3b")
        if not has_ollama and not has_openrouter:
            # Fall back to configured default
            return self._build_decision(RouteTier.LOCAL_FAST, "Defaulting to local Ollama (no keys present)")

        # 3. Measurable signals for CLOUD_DEEP:
        # - Recovery attempt active: failed action needs complex diagnostic reasoning
        if (context.recovery_count or 0) > 0 or context.last_error:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                f"Recovery reasoning required (attempt {context.recovery_count or 0}): {context.last_error or 'previous failure'}",
            )

        # - High complexity flag
        if context.requires_deep_reasoning:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                "Task marked as requiring deep multi-step planning",
            )

        # - Compound goal or long instructions (> 150 chars or multi-clause)
        goal_text = (context.user_goal or "").strip()
        is_compound = any(conj in goal_text.lower() for conj in (" and then ", " after that ", " followed by ", ", then "))
        if is_compound or len(goal_text) > 160:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                "Compound or multi-clause user goal requires deep decomposition",
            )

        # - Deep conversation history (> 8 turns)
        if len(context.conversation_history or []) > 8:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                f"Long dialogue context ({len(context.conversation_history or [])} turns) requires higher capacity",
            )

        # - Many steps already executed in this turn (> 3 steps)
        if (context.step_count or 0) > 3:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                f"Multi-step execution ({context.step_count} steps) transitioning to deep reasoning",
            )

        # - Laya signaled high ambiguity that needs deep synthesis
        if context.is_ambiguous and context.laya_decision and not context.laya_decision.is_confident:
            return self._build_decision(
                RouteTier.CLOUD_DEEP,
                f"Ambiguity with low Laya confidence ({context.laya_decision.confidence:.2f}) requires cloud reasoning",
            )

        # 4. Default for normal, simple, and medium tasks: LOCAL_FAST (Ollama)
        return self._build_decision(
            RouteTier.LOCAL_FAST,
            "Standard single-step/medium task routed to local Ollama 3.2:3b for low latency",
        )

    def _build_decision(self, tier: RouteTier, reason: str) -> ModelRouteDecision:
        if tier == RouteTier.CLOUD_DEEP:
            provider = "openrouter"
            model = model_for_provider("openrouter", self._settings)
            fallback_provider = "ollama"
            fallback_model = model_for_provider("ollama", self._settings)
        else:
            provider = "ollama"
            model = model_for_provider("ollama", self._settings)
            fallback_provider = "openrouter" if is_provider_configured("openrouter", self._settings) else None
            fallback_model = model_for_provider("openrouter", self._settings) if fallback_provider else None

        return ModelRouteDecision(
            tier=tier,
            provider=provider,
            model=model,
            reason=reason,
            fallback_provider=fallback_provider,
            fallback_model=fallback_model,
        )

    def get_client(self, decision: ModelRouteDecision) -> Any:
        """Instantiate or return the active provider client for this decision."""
        return build_provider_client(decision.provider, self._settings)

    def get_fallback_client(self, decision: ModelRouteDecision) -> Any | None:
        """Instantiate fallback provider client if primary fails."""
        if not decision.fallback_provider:
            return None
        try:
            return build_provider_client(decision.fallback_provider, self._settings)
        except Exception as exc:
            logger.warning("Could not build fallback client for %s: %s", decision.fallback_provider, exc)
            return None


default_main_llm_router = MainLLMRouter()
