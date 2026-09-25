"""End-to-End ML Internship search, resume upload, tailoring and validation script."""

import asyncio
import json
import logging
from pathlib import Path

from app.config.settings import get_settings
from app.candidate.analyzer import build_analyzer
from app.graph.workflow import build_workflow
from app.jarvis.orchestrator import default_adapters
from app.sources.searchapi.client import SearchApiClient
from app.sources.searchapi.jobs_adapter import GoogleJobsAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RESUME_TEXT = """
BHANU TEJA SUBBARA
Bengaluru, Karnataka
+91-9618965466 • bhanutejasubbara@gmail.com • linkedin.com/in/bhanuteja12 • github.com/bhanuteja-tech

SUMMARY
M.Tech candidate in CSE with a B.Tech in AI & Data Science (CGPA 8.79). Built and deployed three end-to-end AI/ML applications — including LangGraph-based agentic system and a RAG pipeline with FAISS — covering the full stack from data pipelines to production deployment. Strong in Python, SQL, and LLM-based application development.

EDUCATION
Reva University | M. Tech in Computer Science Engineering (CGPA: 8.9) | 2025-2027
Reva University | B. Tech in Artificial Intelligence and Data Science (CGPA: 8.79) | 2021-2025
Narayana Junior College | Board of Intermediate Education (Percentage: 97%) | 2019-2021

PROJECTS
Olympics Trends and Analysis | Python, Pandas, Matplotlib, Seaborn, Plotly, Streamlit
• Performed EDA on 270k+ Olympic Records to uncover Medal Dominance trends, enabling comparative analysis.
• Deployed the application on Streamlit Community Cloud for public access.

AI Powered News Research Assistant | Python, Streamlit, Lang Chain, FAISS, Vector Embeddings
• Built a dual-mode research tool — OpenAI-Powered semantic mode and offline keyword search mode.
• Designed custom source-balanced retrieval strategy using FAISS with OpenAI text-embedding-3-small.

AI Powered Data Analyst Agent | Python, Streamlit, pandas, LLM Integration
• Built an agent that lets users upload CSV/Excel files and query them in plain English.
• Deployed on Render with Docker; Streamlit frontend talks to FastAPI backend.

TECHNICAL SKILLS
Languages & Data Libraries: Python, SQL, Pandas, NumPy, Scikit-learn
Data Visualization Tools: Tableau, Matplotlib, Seaborn, Plotly, Excel
Technologies/Frameworks: FAISS, Flask, FastAPI, Streamlit, LangChain, LangGraph, RAG pipelines
Developer Tools: VS Code, PyCharm, Jupyter Notebook, Google Colab, MySQL Workbench, Git, GitHub

CERTIFICATIONS/WORKSHOPS
• SQL for Data Science - Coursera
• 100 days of python bootcamp - Udemy
• Basics of Data Science - IBM
• Pandas - Kaggle
• Data Analytics - KPMG
"""

async def run_flow():
    settings = get_settings()
    
    print("=== STEP 1: PARSING RESUME ===")
    res = await build_analyzer(settings).build_profile({"text": RESUME_TEXT})
    candidate_profile = res.profile
    print(f"Candidate: {candidate_profile.identity.full_name}")
    print(f"Technical Skills ({len(candidate_profile.skills.items)}): {[s.name for s in candidate_profile.skills.items]}")
    print(f"Education ({len(candidate_profile.education.items)}): {[e.degree for e in candidate_profile.education.items]}")
    print(f"Certifications ({len(candidate_profile.certifications.items)}): {[c.name for c in candidate_profile.certifications.items]}")
    print(f"Projects ({len(candidate_profile.projects.items)}): {[p.name for p in candidate_profile.projects.items]}")

    print("\n=== STEP 2: FETCHING REAL ML INTERNSHIP JOBS ===")
    async with SearchApiClient(settings) as client:
        adapter = GoogleJobsAdapter(client)
        result = await adapter.fetch_jobs({"searchapi": {"google_jobs": {"q": "Machine Learning Intern Bengaluru"}}})
        print(f"Fetched {len(result.jobs)} jobs from SearchApi.")
        for idx, job in enumerate(result.jobs[:5]):
            print(f"[{idx+1}] {job.title} at {job.company} ({job.location})")

    if not result.jobs:
        print("No live jobs returned, cannot proceed with live tailoring.")
        return

    target_job = result.jobs[0]
    print(f"\n=== STEP 3: RUNNING PHASE 1-6 COMPILED GRAPH ON SEARCH & CANDIDATE ===")
    graph = build_workflow(default_adapters(settings))
    initial_state = {
        "candidate_input": {"text": RESUME_TEXT},
        "search_preferences": {
            "q": "Machine Learning Intern Bengaluru",
            "searchapi": {
                "google_jobs": {"q": "Machine Learning Intern Bengaluru"}
            },
            "tailoring": {"target_job_index": 0}
        }
    }

    final_state = await graph.ainvoke(initial_state)

    print("\n=== STEP 4: GRAPH EXECUTION RESULTS ===")
    print(f"Ranked Jobs: {len(final_state.get('ranked_jobs', []))}")
    print(f"JD Analyses: {len(final_state.get('jd_analyses', {}))}")
    print(f"Match Results: {len(final_state.get('match_results', []))}")
    
    match = final_state.get('match_results', [{}])[0]
    print(f"Match Score: {match.get('score')} ({match.get('tier')})")
    
    tailored = final_state.get('tailored_resume', {})
    print(f"Tailored Summary: {tailored.get('summary')}")
    print(f"Tailored Skills ({len(tailored.get('technical_skills', []))}): {tailored.get('technical_skills')}")
    print(f"Unaddressed JD Requirements: {tailored.get('unaddressed_jd_requirements')}")

    validation = final_state.get('validation_report', {})
    print("\n=== STEP 5: VALIDATION REPORT ===")
    print(f"Overall Status: {validation.get('overall_status')}")
    print(f"Truth Checks Status: {validation.get('truth_checks_status')}")
    print(f"ATS Checks Status: {validation.get('ats_checks_status')}")
    print(f"Confidence: {validation.get('confidence')}")

if __name__ == "__main__":
    asyncio.run(run_flow())
