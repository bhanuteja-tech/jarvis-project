"""Measure execution runtime for:
1. Open YouTube
2. Search LangGraph
3. Open YouTube + Search LangGraph
"""

import asyncio
import sys
import time

sys.path.insert(0, ".")

from app.computer.agent import LLMComputerAgent  # noqa: E402
from app.desktop.observer import ComputerObserver  # noqa: E402
from app.desktop.state import ComputerState  # noqa: E402
from app.desktop.verifier import VerificationService  # noqa: E402
from tests.test_desktop.test_llm_computer_agent import MockHarness  # noqa: E402


async def run_timing_trials():
    # Setup agent
    cs = ComputerState()
    mh = MockHarness(cs)
    agent = LLMComputerAgent(
        state=cs,
        harness=mh,
        observer=ComputerObserver(state=cs),
        verifier=VerificationService(),
    )

    print("--- TRIAL 1: Open YouTube ---")
    t0 = time.perf_counter()
    async for ev in agent.run("Open YouTube"):
        etype = ev.get("agent_event_type")
        if etype in ("step_done", "response"):
            print(f"  [Event {etype}] tool={ev.get('tool')} text={ev.get('text')}")
    d_open = time.perf_counter() - t0
    print(f"Trial 1 (Open YouTube) Duration: {d_open*1000:.2f}ms ({d_open:.4f}s)")

    print("\n--- TRIAL 2: Re-open YouTube (Idempotent Reuse) ---")
    t0 = time.perf_counter()
    async for ev in agent.run("Open YouTube"):
        etype = ev.get("agent_event_type")
        if etype in ("step_done", "response"):
            print(f"  [Event {etype}] tool={ev.get('tool')} text={ev.get('text')}")
    d_reopen = time.perf_counter() - t0
    print(f"Trial 2 (Re-open YouTube) Duration: {d_reopen*1000:.2f}ms ({d_reopen:.4f}s)")

    print("\n--- TRIAL 3: Search LangGraph in Active YouTube Context ---")
    t0 = time.perf_counter()
    async for ev in agent.run("Search LangGraph on YouTube"):
        etype = ev.get("agent_event_type")
        if etype in ("step_done", "response"):
            print(f"  [Event {etype}] tool={ev.get('tool')} text={ev.get('text')}")
    d_search = time.perf_counter() - t0
    print(f"Trial 3 (Search LangGraph) Duration: {d_search*1000:.2f}ms ({d_search:.4f}s)")

    print("\n--- TRIAL 4: Compound 'open youtube and search for LangGraph' ---")
    cs2 = ComputerState()
    mh2 = MockHarness(cs2)
    agent2 = LLMComputerAgent(
        state=cs2,
        harness=mh2,
        observer=ComputerObserver(state=cs2),
        verifier=VerificationService(),
    )
    t0 = time.perf_counter()
    async for ev in agent2.run("open youtube and search for LangGraph"):
        etype = ev.get("agent_event_type")
        if etype in ("step_done", "response"):
            print(f"  [Event {etype}] tool={ev.get('tool')} text={ev.get('text')}")
    d_compound = time.perf_counter() - t0
    ms = d_compound * 1000
    print(f"Trial 4 (Open YouTube + Search LangGraph) Duration: {ms:.2f}ms ({d_compound:.4f}s)")


if __name__ == "__main__":
    asyncio.run(run_timing_trials())
