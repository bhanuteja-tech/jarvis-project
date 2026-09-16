"""Stand-Out Advisor & Gap Analysis Engine.

Diagnoses why a candidate's resume received a particular match score against a JD,
extracts prioritized missing ATS keywords/skills, recommends high-impact standout
portfolio projects tailored to the JD's requirements, and provides actionable bullet
rewrites to help candidates shine compared to other applicants.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.config.settings import Settings

logger = logging.getLogger(__name__)

# Catalog of enterprise-grade, high-impact project archetypes mapped to competencies
_PROJECT_ARCHETYPES: list[dict[str, Any]] = [
    {
        "domain_keys": {
            "pytorch", "tensorflow", "llm", "rag", "transformer", "nlp", "vllm",
            "langchain", "langgraph", "vector", "qdrant", "chroma", "pinecone", "huggingface",
        },
        "title": "Enterprise Multi-Modal RAG Pipeline with Hybrid Retrieval",
        "tagline": "Production neural search engine with hybrid dense-sparse vector indexing",
        "tech_stack": ["PyTorch", "vLLM", "Qdrant", "FastAPI", "Docker", "MLflow", "LangChain"],
        "architecture": (
            "Architected a scalable retrieval-augmented generation (RAG) system utilizing Qdrant "
            "vector store with hybrid BM25 + dense neural reranking (Cross-Encoder). Integrated "
            "vLLM with PagedAttention for token generation, containerized with Docker, and "
            "tracked evaluation metrics (Faithfulness & Answer Relevancy) via MLflow."
        ),
        "metrics": "Achieved <85ms p95 latency on 500k documents; reduced hallucination by 42%.",
        "resume_bullet": (
            "Architected an Enterprise RAG platform using PyTorch and FastAPI; implemented hybrid "
            "dense-sparse retrieval with Qdrant, cutting p95 query latency to <85ms and decreasing "
            "model hallucination by 42% on 500k+ documents."
        ),
        "why_it_stands_out": (
            "Hiring managers look for production serving, vector indexing, latency profiling, and "
            "evaluation metrics rather than trivial notebook scripts."
        ),
    },
    {
        "domain_keys": {
            "distributed", "ray", "deepspeed", "lora", "qlora", "fine-tuning", "gpu",
            "cuda", "scaling", "training", "horovod", "slurm",
        },
        "title": "Distributed LLM Parameter-Efficient Fine-Tuning & Eval Platform",
        "tagline": "Multi-GPU distributed training pipeline with QLoRA & automated evaluation",
        "tech_stack": [
            "PyTorch", "Ray", "DeepSpeed", "QLoRA", "Hugging Face", "Docker", "W&B",
        ],
        "architecture": (
            "Engineered a distributed fine-tuning pipeline utilizing Ray Train and DeepSpeed "
            "ZeRO-2 with 4-bit QLoRA quantisation. Implemented custom loss masking and automated "
            "checkpointing, evaluating domain models against MT-Bench and TruthfulQA."
        ),
        "metrics": "Reduced GPU VRAM consumption by 65% and trained a 14B model 2.8x faster.",
        "resume_bullet": (
            "Engineered a multi-GPU distributed fine-tuning pipeline using PyTorch, Ray, and "
            "DeepSpeed; implemented 4-bit QLoRA, slashing memory overhead by 65% and accelerating "
            "fine-tuning throughput by 2.8x across multi-node clusters."
        ),
        "why_it_stands_out": (
            "Demonstrates rare, high-demand skills in distributed GPU memory management, "
            "parameter-efficient training (PEFT), and multi-node clustering."
        ),
    },
    {
        "domain_keys": {
            "mlops", "mlflow", "kubeflow", "airflow", "docker", "kubernetes", "ci/cd",
            "fastapi", "triton", "prometheus", "grafana", "sagemaker", "dvc",
        },
        "title": "Production MLOps Pipeline with Drift Detection & Continuous Retraining",
        "tagline": "Automated model lifecycle infrastructure with drift alerts & canary rollouts",
        "tech_stack": [
            "MLflow", "FastAPI", "Docker", "Kubernetes", "Airflow", "Evidently AI", "Prometheus",
        ],
        "architecture": (
            "Built a production MLOps pipeline automating dataset versioning (DVC), model "
            "training (Airflow), and model registry (MLflow). Packaged low-latency FastAPI "
            "inference services with Prometheus monitoring for data and concept drift, "
            "triggering automated retraining pipelines."
        ),
        "metrics": "Maintained 99.95% uptime for inference service with canary deployments.",
        "resume_bullet": (
            "Designed and deployed a production MLOps pipeline using MLflow, Docker, and "
            "FastAPI; automated data drift monitoring and continuous retraining with Airflow, "
            "sustaining 99.95% inference availability under 1,200 req/sec loads."
        ),
        "why_it_stands_out": (
            "Bridges research and engineering by proving you can package, monitor, and maintain "
            "models in enterprise production environments."
        ),
    },
    {
        "domain_keys": {
            "agent", "agents", "langgraph", "autogen", "crewai", "tool-calling",
            "function-calling", "mcp", "orchestration", "workflow",
        },
        "title": "Autonomous Multi-Agent Task Orchestrator with Verification Gates",
        "tagline": "Stateful multi-agent system with human-in-the-loop controls & external tools",
        "tech_stack": ["Python", "LangGraph", "FastAPI", "Redis", "Docker", "Pydantic"],
        "architecture": (
            "Developed an autonomous multi-agent reasoning framework using LangGraph with cyclic "
            "state graphs. Implemented tool validation gates, state checkpointing in Redis, and "
            "human-in-the-loop approval mechanisms for secure automated workflows."
        ),
        "metrics": "Executed complex multi-step reasoning workflows with 94% completion rate.",
        "resume_bullet": (
            "Architected a cyclic multi-agent orchestration engine using LangGraph and Redis; "
            "implemented deterministic safety guardrails and asynchronous tool calling, "
            "boosting complex workflow completion rates to 94%."
        ),
        "why_it_stands_out": (
            "Highlights cutting-edge Agentic AI architecture (LangGraph/state graphs) rather "
            "than basic single-prompt wrappers."
        ),
    },
    {
        "domain_keys": {
            "spark", "kafka", "flink", "airflow", "sql", "snowflake", "databricks", "etl", "data",
        },
        "title": "High-Throughput Real-Time Streaming & Feature Store Architecture",
        "tagline": "Sub-second streaming ETL pipeline with Kafka, PySpark, and Redis feature store",
        "tech_stack": ["Apache Kafka", "PySpark", "Redis", "Docker", "PostgreSQL", "Airflow"],
        "architecture": (
            "Built a distributed event streaming engine processing high-velocity JSON events "
            "using Kafka and PySpark Structured Streaming. Materialized low-latency ML feature "
            "stores in Redis and analytical datasets in partitioned Parquet files."
        ),
        "metrics": "Processed 25,000 events/sec with <200ms end-to-end ingestion latency.",
        "resume_bullet": (
            "Constructed a real-time event streaming pipeline with Apache Kafka and PySpark; "
            "ingested 25k events/sec into a Redis feature store, reducing downstream ML feature "
            "serving latency to <15ms."
        ),
        "why_it_stands_out": (
            "Demonstrates real-world data engineering scale and real-time streaming capability "
            "that distinguishes senior candidates."
        ),
    },
    {
        "domain_keys": {
            "backend", "microservices", "grpc", "golang", "go", "redis", "postgresql", "fastapi",
        },
        "title": "Distributed High-Concurrency Microservices Backend with gRPC",
        "tagline": "Event-driven microservices architecture with distributed rate limiting",
        "tech_stack": ["Python / FastAPI", "PostgreSQL", "Redis", "Docker", "gRPC", "RabbitMQ"],
        "architecture": (
            "Designed a distributed backend architecture featuring asynchronous gRPC RPCs, "
            "PostgreSQL connection pooling with SQLAlchemy 2.0, Redis cache warming, and "
            "token-bucket rate limiting."
        ),
        "metrics": "Maintained <35ms latency across 5,000 concurrent active users with zero loss.",
        "resume_bullet": (
            "Engineered a resilient distributed backend architecture using FastAPI, Redis, and "
            "PostgreSQL; implemented asynchronous worker queues and connection pooling, "
            "sustaining 5k concurrent users with <35ms response latency."
        ),
        "why_it_stands_out": (
            "Shows deep systems knowledge, concurrency handling, database indexing, and "
            "resilience."
        ),
    },
]


def _categorize_skill(skill_name: str) -> str:
    """Categorize an ATS skill for structured UI display."""
    s = skill_name.strip().lower()
    if s in {
        "pytorch", "tensorflow", "keras", "scikit-learn", "numpy", "pandas", "scipy",
        "llm", "rag", "transformers", "nlp", "cv", "computer vision", "bert", "gpt",
    }:
        return "Core Technical & Modeling"
    if s in {
        "docker", "kubernetes", "mlflow", "kubeflow", "airflow", "ray", "vllm",
        "fastapi", "flask", "triton", "prometheus", "grafana", "git", "ci/cd", "dvc",
    }:
        return "MLOps, Serving & Infra"
    if s in {
        "python", "go", "golang", "java", "c++", "rust", "typescript", "javascript", "sql", "bash",
    }:
        return "Languages & Runtimes"
    if s in {
        "aws", "gcp", "azure", "s3", "ec2", "sagemaker", "cloud", "lambda", "snowflake",
    }:
        return "Cloud & Big Data"
    return "Domain & Tooling"


def generate_standout_recommendations(
    candidate_profile: Mapping[str, Any] | None,
    job: Mapping[str, Any] | None,
    analysis: Mapping[str, Any] | None,
    match_result: Mapping[str, Any] | None,
    settings: Settings,
) -> dict[str, Any]:
    """Generate complete gap analysis, missing keywords, standout projects, and rewrites."""
    profile_skills_raw = []
    if candidate_profile:
        skills_sec = (candidate_profile.get("profile") or {}).get("skills") or {}
        taxonomy = skills_sec.get("taxonomy") or {}
        for cat_skills in taxonomy.values():
            if isinstance(cat_skills, list):
                for sk in cat_skills:
                    name = sk.get("name") if isinstance(sk, dict) else str(sk)
                    if name:
                        profile_skills_raw.append(str(name).strip().lower())

    candidate_skills_set = set(profile_skills_raw)

    # Extract JD required and preferred skills
    jd_analysis = analysis or {}
    if "analysis" in jd_analysis and isinstance(jd_analysis["analysis"], dict):
        jd_analysis = jd_analysis["analysis"]
    skills_sec = jd_analysis.get("skills") if isinstance(jd_analysis.get("skills"), dict) else {}

    skills_req = jd_analysis.get("skills_required") or skills_sec.get("required") or []
    skills_pref = jd_analysis.get("skills_preferred") or skills_sec.get("preferred") or []
    skills_keywords = skills_sec.get("keywords") or []

    # Also check match_result missing_requirements if available
    missing_from_match = []
    if match_result and isinstance(match_result.get("missing_requirements"), list):
        missing_from_match = match_result["missing_requirements"]

    missing_required: list[dict[str, Any]] = []
    missing_preferred: list[dict[str, Any]] = []

    for item in list(skills_req) + list(missing_from_match):
        name = item.get("name") if isinstance(item, dict) else str(item)
        if not name:
            continue
        cleaned = str(name).strip()
        low = cleaned.lower()
        if (
            low not in candidate_skills_set
            and not any(low == cs or (len(low) > 3 and low in cs) for cs in candidate_skills_set)
            and not any(m["name"].lower() == low for m in missing_required)
        ):
            missing_required.append({
                "name": cleaned,
                "importance": "required",
                "category": _categorize_skill(cleaned),
                "reason": "Explicitly required in the job description qualifications",
            })

    for item in list(skills_pref) + list(skills_keywords):
        name = item.get("name") if isinstance(item, dict) else str(item)
        if not name:
            continue
        cleaned = str(name).strip()
        low = cleaned.lower()
        if (
            low not in candidate_skills_set
            and not any(low == cs or (len(low) > 3 and low in cs) for cs in candidate_skills_set)
            and not any(m["name"].lower() == low for m in missing_required)
            and not any(m["name"].lower() == low for m in missing_preferred)
        ):
            missing_preferred.append({
                "name": cleaned,
                "importance": "preferred",
                "category": _categorize_skill(cleaned),
                "reason": "Preferred qualification that boosts applicant ranking score",
            })

    all_missing = missing_required + missing_preferred

    # Compute current score & simulated projected score
    current_score = 50.0
    if match_result:
        raw_sc = match_result.get("score")
        if isinstance(raw_sc, (int, float)):
            current_score = float(raw_sc)

    simulated_boost = min(42.0, len(missing_required) * 8.0 + len(missing_preferred) * 3.5 + 15.0)
    projected_score = min(96.0, round(current_score + simulated_boost, 1))

    # Identify JD context keywords for project matching
    job_desc = str((job or {}).get("description") or "").lower()
    job_title = str((job or {}).get("title") or "").lower()
    jd_tokens = set(job_desc.split() + job_title.split())
    for ms in all_missing:
        jd_tokens.update(ms["name"].lower().split())

    # Select best standout projects based on domain keyword overlap
    scored_projects: list[tuple[int, dict[str, Any]]] = []
    for archetype in _PROJECT_ARCHETYPES:
        overlap = len(archetype["domain_keys"].intersection(jd_tokens))
        stack_overlap = sum(
            1 for t in archetype["tech_stack"]
            if any(t.lower() == ms["name"].lower() for ms in all_missing)
        )
        scored_projects.append((overlap * 2 + stack_overlap * 3, archetype))

    scored_projects.sort(key=lambda x: x[0], reverse=True)

    # Return top 3 standout projects
    standout_projects: list[dict[str, Any]] = []
    for idx, (_, proj) in enumerate(scored_projects[:3]):
        addressed = [
            ms["name"] for ms in all_missing
            if ms["name"].lower() in [t.lower() for t in proj["tech_stack"]]
            or any(k in ms["name"].lower() for k in proj["domain_keys"])
        ]
        standout_projects.append({
            "id": f"proj_standout_{idx+1}",
            "title": proj["title"],
            "tagline": proj["tagline"],
            "tech_stack": proj["tech_stack"],
            "architecture": proj["architecture"],
            "metrics": proj["metrics"],
            "resume_bullet": proj["resume_bullet"],
            "why_it_stands_out": proj["why_it_stands_out"],
            "addressed_skills": addressed[:4],
        })

    # Bullet point enhancement suggestions based on JD responsibilities
    bullet_suggestions: list[dict[str, Any]] = []
    resp_sec = jd_analysis.get("responsibilities")
    responsibilities = resp_sec.get("items") if isinstance(resp_sec, dict) else (resp_sec or [])
    if not responsibilities and job_desc:
        raw_lines = [
            line.strip().lstrip("-*• ").strip()
            for line in job_desc.splitlines()
        ]
        responsibilities = [line for line in raw_lines if len(line) > 30][:3]

    for resp in responsibilities[:3]:
        resp_text = resp if isinstance(resp, str) else str(resp.get("text", ""))
        if not resp_text:
            continue
        bullet_suggestions.append({
            "target_area": "Experience / Project Impact",
            "suggested_bullet": (
                f"Spearheaded initiatives to {resp_text.rstrip('.')}, designing scalable "
                "solutions with automated testing and measurable throughput improvements."
            ),
            "reason": f"Directly mirrors key responsibility from JD: \"{resp_text[:50]}...\"",
        })

    gap_summary = (
        f"Your resume matches {current_score:.0f}% of this role's criteria. You have strong "
        f"competencies, but adding {len(missing_required)} missing required keyword(s) and a "
        f"production-grade portfolio project will elevate your fit to ~{projected_score:.0f}%, "
        "placing you in the top tier of candidates."
    )

    return {
        "current_score": current_score,
        "projected_score": projected_score,
        "gap_summary": gap_summary,
        "missing_skills": all_missing,
        "missing_required_count": len(missing_required),
        "missing_preferred_count": len(missing_preferred),
        "standout_projects": standout_projects,
        "bullet_suggestions": bullet_suggestions,
        "unaddressed_requirements": [m["name"] for m in missing_required],
    }
