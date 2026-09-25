"""Comprehensive Router tests covering required benchmark cases A through T.

Ensures strict separation between computer tasks, browser operations, and career searches.
"""

from app.routing.router import default_router
from app.routing.taxonomy import Intent


def test_case_a_open_vs_code():
    res = default_router.route("Open VS Code.")
    assert res.intent == Intent.OPEN_APPLICATION
    assert res.params.get("application") == "visual_studio_code"


def test_case_b_open_microsoft_edge():
    res = default_router.route("Open Microsoft Edge.")
    assert res.intent == Intent.OPEN_APPLICATION
    assert res.params.get("application") == "microsoft_edge"


def test_case_c_open_chrome():
    res = default_router.route("Open Chrome.")
    assert res.intent == Intent.OPEN_APPLICATION
    assert res.params.get("application") == "google_chrome"


def test_case_d_open_file_explorer():
    res = default_router.route("Open File Explorer.")
    assert res.intent == Intent.OPEN_APPLICATION
    assert res.params.get("application") == "file_explorer"


def test_case_e_open_desktop():
    res = default_router.route("Open Desktop.")
    assert res.intent == Intent.OPEN_FOLDER
    assert res.params.get("target") == "desktop"


def test_case_f_list_files_on_desktop():
    res = default_router.route("List the files on my Desktop.")
    assert res.intent == Intent.LIST_FILES
    assert res.params.get("directory") == "desktop"


def test_case_g_search_desktop_for_vscode():
    res = default_router.route("Search my Desktop for VS Code.")
    assert res.intent == Intent.SEARCH_FILES
    assert res.params.get("directory") == "desktop"
    assert "code" in res.params.get("query", "").lower()


def test_case_h_open_resume():
    res = default_router.route("Open my resume from the Desktop.")
    assert res.intent == Intent.OPEN_FILE
    assert res.params.get("query") == "resume" or res.params.get("target") == "desktop"


def test_case_i_search_youtube_for_campus_x():
    res = default_router.route("Search YouTube for Campus X.")
    assert res.intent == Intent.BROWSER_SEARCH
    assert res.params.get("service") == "youtube"
    assert "campus x" in res.params.get("query", "").lower()


def test_case_j_search_web_for_fastapi():
    res = default_router.route("Search the web for FastAPI.")
    assert res.intent == Intent.BROWSER_SEARCH
    assert "fastapi" in res.params.get("query", "").lower()


def test_case_k_find_data_scientist_jobs():
    res = default_router.route("Find me Data Scientist jobs.")
    assert res.intent == Intent.CAREER_JOB_SEARCH
    assert "data scientist" in res.params.get("query", "").lower()


def test_case_l_find_ml_internships_in_bangalore():
    res = default_router.route("Find ML internships in Bangalore.")
    assert res.intent == Intent.CAREER_JOB_SEARCH
    assert "internships" in res.params.get("query", "").lower()


def test_case_m_open_vs_code_and_open_project():
    res = default_router.route("Open VS Code and then open my project.")
    assert res.is_compound
    assert res.plan is not None
    assert len(res.plan.steps) >= 2
    assert res.plan.steps[0].intent == Intent.OPEN_APPLICATION
    assert res.plan.steps[1].intent == Intent.OPEN_FOLDER


def test_case_n_three_step_browser_plan():
    res = default_router.route("Open Chrome, go to YouTube, and search Campus X.")
    assert res.is_compound
    assert res.plan is not None
    assert len(res.plan.steps) == 3
    assert res.plan.steps[0].intent == Intent.OPEN_APPLICATION
    assert res.plan.steps[1].intent == Intent.BROWSER_NAVIGATE
    assert res.plan.steps[2].intent == Intent.BROWSER_SEARCH


def test_case_o_correction_not_bs_code_open_vs_code():
    res = default_router.route("it's not BS code, open VS code.")
    assert res.is_correction
    assert res.intent == Intent.OPEN_APPLICATION
    assert res.params.get("application") == "visual_studio_code"


def test_case_p_navigate_desktop_and_search_vscode():
    res = default_router.route("navigate to my Desktop and search for vscode.")
    assert res.is_compound
    assert res.plan is not None
    assert res.plan.steps[0].intent == Intent.OPEN_FOLDER
    assert res.plan.steps[1].intent == Intent.SEARCH_FILES
    assert res.intent != Intent.CAREER_JOB_SEARCH


def test_case_q_find_my_resume():
    res = default_router.route("find my resume.")
    assert res.intent in {Intent.SEARCH_FILES, Intent.OPEN_FILE}
    assert res.intent != Intent.CAREER_JOB_SEARCH


def test_case_r_find_vscode_on_my_computer():
    res = default_router.route("find VS Code on my computer.")
    assert res.intent in {Intent.SEARCH_FILES, Intent.OPEN_APPLICATION}
    assert res.intent != Intent.CAREER_JOB_SEARCH


def test_case_s_search_for_data_scientist_jobs():
    res = default_router.route("search for data scientist jobs.")
    assert res.intent == Intent.CAREER_JOB_SEARCH


def test_case_t_search_youtube_for_data_scientist_jobs():
    res = default_router.route("search YouTube for data scientist jobs.")
    assert res.intent == Intent.BROWSER_SEARCH
    assert res.params.get("service") == "youtube"
    assert res.intent != Intent.CAREER_JOB_SEARCH


def test_case_open_desktop_in_it():
    res = default_router.route("Open Desktop in it.")
    assert res.intent == Intent.OPEN_FOLDER
    assert res.params.get("target") == "desktop"


def test_case_contextual_ordinals():
    res1 = default_router.route("first one")
    assert res1.intent == Intent.OPEN_FILE
    assert res1.params.get("index") == 0
    assert res1.intent != Intent.CAREER_JOB_SEARCH

    res2 = default_router.route("the first one")
    assert res2.intent == Intent.OPEN_FILE
    assert res2.params.get("index") == 0

    res3 = default_router.route("open the second one")
    assert res3.intent == Intent.OPEN_FILE
    assert res3.params.get("index") == 1


def test_case_search_for_langgraph_in_youtube():
    res = default_router.route("Search for LangGraph in YouTube.")
    assert res.intent == Intent.BROWSER_SEARCH
    assert res.params.get("service") == "youtube"
    assert "langgraph" in res.params.get("query", "").lower()


def test_case_search_langgraph_in_youtube_bare():
    res = default_router.route("Search LangGraph in YouTube.")
    assert res.intent == Intent.BROWSER_SEARCH
    assert res.params.get("service") == "youtube"
    assert "langgraph" in res.params.get("query", "").lower()


def test_case_open_whatsapp_and_message_lohit():
    res = default_router.route("Open WhatsApp and message Lohit saying hi.")
    assert res.is_compound
    assert res.plan is not None
    assert len(res.plan.steps) == 2
    assert res.plan.steps[0].intent == Intent.OPEN_APPLICATION
    assert res.plan.steps[1].intent == Intent.MESSAGING_SEND
    assert res.plan.steps[1].params.get("recipient", "").lower() == "lohit"


def test_case_confirmation_yes_send_it():
    res = default_router.route("Yes, send it.")
    assert res.intent == Intent.CONFIRM_ACTION
    assert res.params.get("confirmed") is True

