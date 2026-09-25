import sys
sys.path.insert(0, ".")
import asyncio
from app.computer.agent import LLMComputerAgent
from app.desktop.state import ComputerState
from tests.test_desktop.test_llm_computer_agent import MockHarness

async def main():
    cs = ComputerState()
    mh = MockHarness(cs)
    ag = LLMComputerAgent(state=cs, harness=mh)
    async for ev in ag.run("Go back."):
        print(ev.get("agent_event_type"), ev.get("tool"), ev.get("text"))

if __name__ == "__main__":
    asyncio.run(main())
