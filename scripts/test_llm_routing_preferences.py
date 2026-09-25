"""Verification script for intelligent model routing and session preferences."""

import asyncio
from app.config.settings import get_settings
from app.llm import create_assistant_llm
from app.llm.preferences import preference_store
from app.llm.router import RoutingAssistantClient

async def test_routing():
    settings = get_settings()
    print("=== CONFIGURATION ===")
    print("Master Assistant LLM Enabled:", settings.jarvis_assistant_llm_enabled)
    print("Routing Enabled:", settings.jarvis_llm_routing_enabled)
    print("Default Provider:", settings.jarvis_llm_routing_default or settings.jarvis_llm_provider)

    llm = create_assistant_llm(settings)
    print("Is Routing Client:", isinstance(llm, RoutingAssistantClient))

    print("\n=== TEST 1: DEFAULT ROUTING (Ollama / local) ===")
    resp1 = await llm.generate(system_prompt="You are a helpful AI assistant.", user_prompt="Say 'Ollama is online' in 5 words.")
    print("Ollama Response:", resp1)

    print("\n=== TEST 2: PREFERENCE OVERRIDE (OpenRouter / cloud) ===")
    session_id = "test-session-123"
    preference_store.save(
        session_id,
        settings=settings,
        payload={
            "routing_enabled": True,
            "preferred_provider": "openrouter"
        }
    )
    prefs = preference_store.get(session_id)
    print("Saved Session Preferences:", prefs)

    openrouter_llm = RoutingAssistantClient(
        settings,
        router=llm._router,
        task="chat",
        preferred_provider=prefs.preferred_provider,
    )

    resp2 = await openrouter_llm.generate(system_prompt="You are a helpful AI assistant.", user_prompt="Say 'OpenRouter is online' in 5 words.")
    print("OpenRouter Response:", resp2)

if __name__ == "__main__":
    asyncio.run(test_routing())
