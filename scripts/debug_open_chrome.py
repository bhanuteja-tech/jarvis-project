import sys
sys.path.insert(0, ".")
import asyncio
from app.computer.agent import LLMComputerAgent
from app.desktop.state import ComputerState
from app.desktop.observer import ComputerObserver
from app.desktop.verifier import VerificationService
from tests.test_desktop.test_llm_computer_agent import MockHarness

async def main():
    cs = ComputerState()
    mh = MockHarness(cs)
    ag = LLMComputerAgent(
        state=cs,
        harness=mh,
        observer=ComputerObserver(state=cs),
        verifier=VerificationService(),
    )
    async for ev in ag.run("Open Chrome."):
        print(f"event={ev.get('agent_event_type')} tool={ev.get('tool')} action={ev.get('action')} text={ev.get('text')} decision={ev.get('decision')}")

if __name__ == "__main__":
    asyncio.run(main())
