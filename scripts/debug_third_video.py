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
    ag.typed_context.set_youtube_entities([
        {"title": "LangGraph Tutorial 1", "url": "https://www.youtube.com/watch?v=lg_1"},
        {"title": "LangGraph Tutorial 2", "url": "https://www.youtube.com/watch?v=lg_2"},
        {"title": "LangGraph Tutorial 3", "url": "https://www.youtube.com/watch?v=lg_3"},
    ])
    ag.state.web_context.site = "youtube"
    async for ev in ag.run("Open the third video."):
        print(f"event={ev.get('agent_event_type')} tool={ev.get('tool')} text={ev.get('text')}")

if __name__ == "__main__":
    asyncio.run(main())
