"""Laya System-1 vs Main LLM Benchmark Suite for JARVIS.

Benchmarks 10 canonical JARVIS tasks measuring:
- Laya System-1 latency
- Ollama local model latency
- Escalation rate
- System-1 confidence and accuracy
- Total decision latency
Stores results to benchmark_results.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest

from app.llm.decision_engine import DecisionEngine, get_decision_engine
from app.llm.main_router import MainLLMRouter, TaskContext, default_main_llm_router

logger = logging.getLogger(__name__)

BENCHMARK_CASES = [
    {
        "id": "1_filesystem_intent",
        "description": "Filesystem domain intent classification",
        "utterance": "how many files are present in music",
        "question": "What domain does this request belong to?",
        "options": ["filesystem", "browser", "application", "messaging"],
        "expected": "filesystem",
        "type": "choice",
    },
    {
        "id": "2_browser_intent",
        "description": "Browser domain intent classification",
        "utterance": "search LangGraph tutorials on YouTube",
        "question": "What domain does this request belong to?",
        "options": ["filesystem", "browser", "application", "messaging"],
        "expected": "browser",
        "type": "choice",
    },
    {
        "id": "3_application_intent",
        "description": "Application launch intent",
        "utterance": "open Notepad",
        "question": "What domain does this request belong to?",
        "options": ["filesystem", "browser", "application", "messaging"],
        "expected": "application",
        "type": "choice",
    },
    {
        "id": "4_pronoun_it",
        "description": "Contextual pronoun 'it' resolution",
        "utterance": "what is inside it",
        "question": "Which entity does 'it' refer to?",
        "options": ["C:/Users/Music", "Google Chrome", "Desktop"],
        "expected": "C:/Users/Music",
        "type": "choice",
    },
    {
        "id": "5_pronoun_those",
        "description": "Contextual pronoun 'those' resolution",
        "utterance": "what are those files",
        "question": "What do 'those' refer to?",
        "options": ["previous directory listing", "browser tabs", "running processes"],
        "expected": "previous directory listing",
        "type": "choice",
    },
    {
        "id": "6_ordinal_third_one",
        "description": "Ordinal reference resolution",
        "utterance": "open the third one",
        "question": "Which candidate is selected?",
        "options": ["file_a.txt", "file_b.pdf", "file_c.zip", "file_d.py"],
        "expected": "file_c.zip",
        "type": "choice",
    },
    {
        "id": "7_ambiguity_detection",
        "description": "Ambiguity gate on vague utterance",
        "utterance": "open that",
        "question": "Is this request ambiguous?",
        "context_summary": "4 windows, 6 tabs, 12 files",
        "expected": True,
        "type": "noul",
    },
    {
        "id": "8_simple_tool_choice",
        "description": "Tool shortlist candidate selection",
        "utterance": "count how many items are in downloads",
        "question": "Which tool matches this request?",
        "options": ["count_directory_items", "browser_search", "open_application", "send_message"],
        "expected": "count_directory_items",
        "type": "choice",
    },
    {
        "id": "9_semantic_verification",
        "description": "Verification of observed state against user goal",
        "expected_goal": "open Music folder",
        "observed_evidence": "File Explorer active at C:/Users/Music",
        "question": "Does the observed state represent success?",
        "expected": True,
        "type": "noul",
    },
    {
        "id": "10_whatsapp_recipient",
        "description": "Messaging recipient selection",
        "utterance": "send hi to Lohit",
        "question": "Which contact is the recipient?",
        "options": ["Lohit", "Bhanu", "Mom", "Office Group"],
        "expected": "Lohit",
        "type": "choice",
    },
]


@pytest.mark.asyncio
async def test_run_laya_benchmarks():
    engine: DecisionEngine = get_decision_engine()
    router: MainLLMRouter = default_main_llm_router

    # Warm-up call so initialization overhead doesn't distort runtime inference latency
    if hasattr(engine, "initialize"):
        await engine.initialize()
    await engine.choice("warmup", "question", ["opt1", "opt2"])

    results: list[dict[str, Any]] = []
    total_laya_lat_ms = 0.0
    correct_count = 0
    escalations = 0

    for case in BENCHMARK_CASES:
        t0 = time.perf_counter()
        qtype = case.get("type", "choice")

        if qtype == "choice":
            dec_res = await engine.choice(
                context=case.get("utterance", ""),
                question=case.get("question", ""),
                options=case.get("options", []),
            )
        elif qtype == "noul":
            if "expected_goal" in case:
                dec_res = await engine.semantic_verify(
                    expected_goal=case["expected_goal"],
                    observed_evidence=case["observed_evidence"],
                )
            else:
                dec_res = await engine.is_ambiguous(
                    utterance=case["utterance"],
                    context_summary=case.get("context_summary", ""),
                )
        else:
            dec_res = await engine.choice(
                context=case.get("utterance", ""),
                question=case.get("question", ""),
                options=case.get("options", []),
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_laya_lat_ms += elapsed_ms

        is_accurate = (dec_res.decision == case["expected"])
        if is_accurate:
            correct_count += 1

        # Check if LLM router escalates based on confidence or ambiguity
        task_ctx = TaskContext(
            user_goal=case.get("utterance", ""),
            laya_decision=dec_res,
            is_ambiguous=(dec_res.decision is True if qtype == "noul" and "ambiguous" in case["id"] else False),
        )
        route_decision = router.route(task_ctx)
        if route_decision.tier.value == "cloud_deep":
            escalations += 1

        results.append({
            "case_id": case["id"],
            "description": case["description"],
            "qtype": qtype,
            "decision": str(dec_res.decision),
            "expected": str(case["expected"]),
            "confidence": round(dec_res.confidence, 4),
            "accurate": is_accurate,
            "laya_latency_ms": round(elapsed_ms, 2),
            "llm_route_tier": route_decision.tier.value,
            "llm_model": route_decision.model,
        })

    avg_latency = total_laya_lat_ms / len(BENCHMARK_CASES)
    accuracy = correct_count / len(BENCHMARK_CASES)
    escalation_rate = escalations / len(BENCHMARK_CASES)

    summary = {
        "benchmark_timestamp": time.time(),
        "total_cases": len(BENCHMARK_CASES),
        "accurate_cases": correct_count,
        "accuracy_pct": round(accuracy * 100, 1),
        "avg_laya_latency_ms": round(avg_latency, 2),
        "escalation_count": escalations,
        "escalation_rate_pct": round(escalation_rate * 100, 1),
        "results": results,
    }

    # Store benchmark artifacts
    out_path = Path("tests/test_laya/benchmark_results.json")
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    root_out_path = Path("benchmark_results_laya.json")
    root_out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    assert accuracy >= 0.80, f"Benchmark accuracy {accuracy * 100:.1f}% below 80%"
    assert avg_latency < 50.0, f"System-1 latency {avg_latency:.2f}ms too high for fast decisions"
