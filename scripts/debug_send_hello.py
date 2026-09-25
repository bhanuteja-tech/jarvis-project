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
    # Check decision returned by agent._decide_next_action
    dec, tele = await ag._decide_next_action("Send hello to Lohit.", 0, 0, None)
    print("DECISION:", dec)
    print("TELEMETRY:", tele)

if __name__ == "__main__":
    asyncio.run(main())
