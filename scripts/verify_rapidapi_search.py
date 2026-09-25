"""Script to verify RapidAPI adapter live search and resume tailoring."""

import asyncio
import logging
from app.config.settings import get_settings
from app.candidate.analyzer import build_analyzer
from app.sources.rapidapi.client import RapidApiClient
from app.sources.rapidapi.adapter import RapidApiAdapter
from app.graph.workflow import build_workflow
from app.jarvis.orchestrator import default_adapters

logging.basicConfig(level=logging.INFO)

RESUME_TEXT = """
BHANU TEJA SUBBARA
Bengaluru, Karnataka
+91-9618965466 • bhanutejasubbara@gmail.com • linkedin.com/in/bhanuteja12 • github.com/bhanuteja-tech

SUMMARY
M.Tech candidate in CSE with a B.Tech in AI & Data Science (CGPA 8.79). Built and deployed three end-to-end AI/ML applications — including LangGraph-based agentic system and a RAG pipeline with FAISS — covering the full stack from data pipelines to production deployment. Strong in Python, SQL, and LLM-based application development.

EDUCATION
Reva University | M. Tech in Computer Science Engineering (CGPA: 8.9) | 2025-2027
Reva University | B. Tech in Artificial Intelligence and Data Science (CGPA: 8.79) | 2021-2025

PROJECTS
Olympics Trends and Analysis | Python, Pandas, Matplotlib, Seaborn, Plotly, Streamlit
• Performed EDA on 270k+ Olympic Records to uncover Medal Dominance trends.

AI Powered News Research Assistant | Python, Streamlit, LangChain, FAISS, Vector Embeddings
• Built a dual-mode research tool with FAISS and OpenAI text-embeddings.

AI Powered Data Analyst Agent | Python, Streamlit, pandas, LLM Integration
• Built an agent that lets users upload CSV/Excel files and query them in plain English.

TECHNICAL SKILLS
Languages & Data Libraries: Python, SQL, Pandas, NumPy, Scikit-learn
Data Visualization Tools: Tableau, Matplotlib, Seaborn, Plotly, Excel
Technologies/Frameworks: FAISS, Flask, FastAPI, Streamlit, LangChain, LangGraph, RAG pipelines
Developer Tools: VS Code, PyCharm, Jupyter Notebook, Google Colab, MySQL Workbench, Git, GitHub
"""

async def run_rapidapi_verification():
    settings = get_settings()
    key = settings.rapidapi_api_key.get_secret_value().strip() or settings.x_rapidapi_key.get_secret_value().strip()
    
    print(f"=== RAPIDAPI CONFIGURATION CHECK ===")
    print(f"RapidAPI Key present: {bool(key)}")
    print(f"RapidAPI Host: {settings.rapidapi_host}")

    print("\n=== STEP 1: TESTING RAPIDAPI ADAPTER DIRECTLY ===")
    queries = ["Data Scientist Bengaluru", "Python Developer India", "Machine Learning Engineer"]
    
    try:
        async with RapidApiClient(settings) as client:
            adapter = RapidApiAdapter(client)
            for q in queries:
                print(f"\nSearching RapidAPI for: '{q}'...")
                res = await adapter.fetch_jobs({"rapidapi": {"query": q}})
                print(f"Raw Count: {res.raw_count}, Normalized Jobs: {len(res.jobs)}, Errors: {len(res.errors)}, Warnings: {len(res.warnings)}")
                for idx, job in enumerate(res.jobs[:3]):
                    print(f"  [{idx+1}] {job.title} at {job.company} ({job.location})")
    except Exception as exc:
        print(f"RapidAPI Call Status: {exc}")

    print("\n=== STEP 2: TESTING GRAPH DISCOVERY & TAILORING WITH REGISTERED ADAPTERS ===")
    adapters = default_adapters(settings)
    adapter_names = [type(a).__name__ for a in adapters]
    print(f"Active Registered Adapters in Orchestrator ({len(adapters)}): {adapter_names}")

    graph = build_workflow(adapters)
    initial_state = {
        "candidate_input": {"text": RESUME_TEXT},
        "search_preferences": {
            "q": "Machine Learning Engineer Bengaluru",
            "searchapi": {"google_jobs": {"q": "Machine Learning Engineer Bengaluru"}},
            "rapidapi": {"query": "Machine Learning Engineer Bengaluru"},
            "tailoring": {"target_job_index": 0}
        }
    }

    final_state = await graph.ainvoke(initial_state)

    print("\n=== STEP 3: GRAPH PIPELINE OUTPUT ===")
    jobs = final_state.get("jobs", [])
    matches = final_state.get("match_results", [])
    tailored = final_state.get("tailored_resume", {})
    validation = final_state.get("validation_report", {})

    print(f"Total Discovered Jobs: {len(jobs)}")
    print(f"Matched Jobs: {len(matches)}")
    if matches:
        print(f"Top Match: {matches[0].get('score')} ({matches[0].get('tier')})")
    
    print("\nTailored Resume Details:")
    print(f"Target Role: {tailored.get('target_role')}")
    print(f"Target Company: {tailored.get('target_company')}")
    print(f"Summary: {tailored.get('summary')}")
    print(f"Technical Skills: {tailored.get('technical_skills')}")

    print("\nValidation Status:")
    print(f"Overall Status: {validation.get('overall_status')}")
    print(f"Truth Checks Status: {validation.get('truth_checks_status')}")
    print(f"ATS Checks Status: {validation.get('ats_checks_status')}")
    print(f"Confidence: {validation.get('confidence')}")

if __name__ == "__main__":
    asyncio.run(run_rapidapi_verification())
