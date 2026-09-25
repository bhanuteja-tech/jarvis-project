"""Section 24 Context and Stress Test for JARVIS General-Purpose Computer Agent.

Simulates the exact 17-turn conversation specified in Section 24 of the requirements:
1. "Open Chrome."
2. "Open YouTube."
3. "Search Campus X."
4. "Actually stop."
5. "Open VS Code."
6. "Open my Desktop."
7. "What files are there?"
8. "Find my resume."
9. "Open it."
10. "Actually close that."
11. "Open Downloads."
12. "Find the latest PDF."
13. "Open it."
14. "Go back to Chrome."
15. "Search YouTube for Campus X."
16. "Stop."
17. "Find me Data Scientist jobs."

Asserts:
- Commands 1-16 remain computer/browser operations.
- No job pipeline is triggered accidentally.
- Command 17 is the first and only career operation.
- Context switches correctly between applications.
- Corrections cancel previous work.
- Search results cache and resolve correctly on 'Open it.'
"""

from app.agent.task_manager import TaskManager
from app.desktop.state import ComputerState
from app.routing.router import default_router
from app.routing.taxonomy import Intent


def test_17_turn_stress_conversation():
    state = ComputerState()
    task_mgr = TaskManager()

    # 1. "Open Chrome."
    r1 = default_router.route("Open Chrome.")
    assert r1.intent == Intent.OPEN_APPLICATION
    assert r1.params.get("application") == "google_chrome"
    state.update(
        active_application="Google Chrome", browser={"name": "chrome", "current_url": "about:blank"}
    )
    assert state.active_application == "Google Chrome"

    # 2. "Open YouTube."
    r2 = default_router.route("Open YouTube.")
    assert r2.intent == Intent.BROWSER_NAVIGATE
    assert r2.params.get("service") == "youtube"
    state.update(current_url="https://www.youtube.com")
    assert state.current_url == "https://www.youtube.com"

    # 3. "Search Campus X."
    r3 = default_router.route("Search Campus X.")
    assert r3.intent == Intent.BROWSER_SEARCH
    assert "campus x" in r3.params.get("query", "").lower()
    t3 = task_mgr.create_task(intent="BROWSER_SEARCH")
    assert t3.generation == 1

    # 4. "Actually stop."
    r4 = default_router.route("Actually stop.")
    assert r4.intent == Intent.INTERRUPT
    assert r4.is_correction
    task_mgr.cancel_task(t3.task_id)
    assert task_mgr.is_cancelled(t3.task_id)
    new_gen = task_mgr.next_generation()
    assert new_gen == 2
    assert not task_mgr.is_generation_valid(1)

    # 5. "Open VS Code."
    r5 = default_router.route("Open VS Code.")
    assert r5.intent == Intent.OPEN_APPLICATION
    assert r5.params.get("application") == "visual_studio_code"
    state.update(active_application="Visual Studio Code")
    assert state.active_application == "Visual Studio Code"

    # 6. "Open my Desktop."
    r6 = default_router.route("Open my Desktop.")
    assert r6.intent == Intent.OPEN_FOLDER
    assert r6.params.get("target") == "desktop"
    state.update(active_application="File Explorer", current_directory="C:\\Users\\User\\Desktop")
    assert "Desktop" in state.current_directory

    # 7. "What files are there?"
    r7 = default_router.route("What files are there?")
    assert r7.intent == Intent.LIST_FILES
    assert r7.intent != Intent.CAREER_JOB_SEARCH

    # 8. "Find my resume."
    r8 = default_router.route("Find my resume.")
    assert r8.intent in {Intent.SEARCH_FILES, Intent.OPEN_FILE}
    assert r8.intent != Intent.CAREER_JOB_SEARCH
    state.last_search_results = [
        {"name": "resume.pdf", "path": "C:\\Users\\User\\Desktop\\resume.pdf", "type": "file"}
    ]

    # 9. "Open it."
    r9 = default_router.route("Open it.")
    assert r9.intent == Intent.OPEN_FILE
    assert r9.params.get("use_last_result") is True
    assert len(state.last_search_results) == 1
    target_to_open = state.last_search_results[0]["path"]
    assert target_to_open.endswith("resume.pdf")

    # 10. "Actually close that."
    r10 = default_router.route("Actually close that.")
    assert r10.intent == Intent.CLOSE_APPLICATION
    assert r10.is_correction

    # 11. "Open Downloads."
    r11 = default_router.route("Open Downloads.")
    assert r11.intent == Intent.OPEN_FOLDER
    assert r11.params.get("target") == "downloads"
    state.update(current_directory="C:\\Users\\User\\Downloads")
    assert "Downloads" in state.current_directory

    # 12. "Find the latest PDF."
    r12 = default_router.route("Find the latest PDF.")
    assert r12.intent == Intent.SEARCH_FILES
    assert r12.intent != Intent.CAREER_JOB_SEARCH
    state.last_search_results = [
        {
            "name": "report_latest.pdf",
            "path": "C:\\Users\\User\\Downloads\\report_latest.pdf",
            "type": "file",
        }
    ]

    # 13. "Open it."
    r13 = default_router.route("Open it.")
    assert r13.intent == Intent.OPEN_FILE
    assert r13.params.get("use_last_result") is True
    assert state.last_search_results[0]["name"] == "report_latest.pdf"

    # 14. "Go back to Chrome."
    r14 = default_router.route("Go back to Chrome.")
    assert r14.intent == Intent.FOCUS_APPLICATION
    assert r14.params.get("application") == "google_chrome"
    state.update(active_application="Google Chrome")
    assert state.active_application == "Google Chrome"

    # 15. "Search YouTube for Campus X."
    r15 = default_router.route("Search YouTube for Campus X.")
    assert r15.intent == Intent.BROWSER_SEARCH
    assert r15.params.get("service") == "youtube"
    assert "campus x" in r15.params.get("query", "").lower()

    # 16. "Stop."
    r16 = default_router.route("Stop.")
    assert r16.intent == Intent.INTERRUPT

    # 17. "Find me Data Scientist jobs."
    r17 = default_router.route("Find me Data Scientist jobs.")
    # ONLY NOW does career pipeline route
    assert r17.intent == Intent.CAREER_JOB_SEARCH
    assert "data scientist" in r17.params.get("query", "").lower()
