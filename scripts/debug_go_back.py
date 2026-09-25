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
    ag.state.active_application = "Google Chrome"
    ag.state.current_url = "https://www.youtube.com/results?search_query=langgraph"
    async for ev in ag.run("Go back."):
        print(f"event={ev.get('agent_event_type')} tool={ev.get('tool')} text={ev.get('text')}")

if __name__ == "__main__":
    asyncio.run(main())
