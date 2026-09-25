import asyncio
from app.computer.agent import LLMComputerAgent

async def test():
    agent = LLMComputerAgent()
    
    print("--- TURN 1 ---")
    async for ev in agent.run("how many files are present in music"):
        ev_type = ev.get("agent_event_type")
        if ev_type in ("step_start", "step_done", "response", "task_completed"):
            print(f"[{ev_type}] tool={ev.get('tool')} text={ev.get('text')} response={ev.get('response')}")

    print("\n--- TURN 2 ---")
    async for ev in agent.run("what are those files"):
        ev_type = ev.get("agent_event_type")
        if ev_type in ("step_start", "step_done", "response", "task_completed"):
            print(f"[{ev_type}] tool={ev.get('tool')} text={ev.get('text')} response={ev.get('response')}")

    print("\n--- TURN 3 ---")
    async for ev in agent.run("open the third one"):
        ev_type = ev.get("agent_event_type")
        if ev_type in ("step_start", "step_done", "response", "task_completed"):
            print(f"[{ev_type}] tool={ev.get('tool')} text={ev.get('text')} response={ev.get('response')}")

if __name__ == "__main__":
    asyncio.run(test())
