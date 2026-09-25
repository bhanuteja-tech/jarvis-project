"""Tests for Laya Decision Engine and System-1 Fast Primitives."""

from __future__ import annotations

import pytest

from app.llm.decision_engine import (
    DecisionEngine,
    DecisionResult,
    DeterministicDecisionEngine,
    LayaDecisionEngine,
    get_decision_engine,
)


@pytest.fixture
def deterministic_engine() -> DeterministicDecisionEngine:
    return DeterministicDecisionEngine()


@pytest.fixture
def fallback_engine() -> LayaDecisionEngine:
    # Laya disabled to test robust fallback
    return LayaDecisionEngine(enabled=False)


# 1. Output Schema Validation
def test_decision_result_schema():
    res = DecisionResult(
        decision="filesystem",
        confidence=0.92,
        probabilities={"filesystem": 0.92, "browser": 0.08},
        qtype="choice",
        latency_ms=12.5,
        available=True,
        reason="Laya test",
    )
    d = res.to_dict()
    assert d["decision"] == "filesystem"
    assert d["confidence"] == 0.92
    assert d["probabilities"]["filesystem"] == 0.92
    assert d["qtype"] == "choice"
    assert d["latency_ms"] == 12.5
    assert d["available"] is True
    assert res.is_confident is True


# 2. Domain Classification
@pytest.mark.asyncio
async def test_domain_classification(deterministic_engine: DecisionEngine):
    res_fs = await deterministic_engine.classify_domain(
        "how many files are present in music",
        active_app="File Explorer",
        current_dir="C:/Users/Music",
    )
    assert res_fs.decision == "filesystem"
    assert res_fs.confidence >= 0.85

    res_browser = await deterministic_engine.classify_domain(
        "search LangGraph tutorials on YouTube",
        active_app="Google Chrome",
        current_url="https://youtube.com",
    )
    assert res_browser.decision == "browser"
    assert res_browser.confidence >= 0.85


# 3. Filesystem vs Browser Separation
@pytest.mark.asyncio
async def test_filesystem_vs_browser_separation(deterministic_engine: DecisionEngine):
    fs_dec = await deterministic_engine.classify_domain(
        "list the items in downloads",
        active_app="File Explorer",
    )
    assert fs_dec.decision == "filesystem"
    assert fs_dec.decision != "browser"

    br_dec = await deterministic_engine.classify_domain(
        "go to github.com and open notifications",
        active_app="Google Chrome",
    )
    assert br_dec.decision == "browser"
    assert br_dec.decision != "filesystem"


# 4. Reference Resolution ('it', 'those', 'the third one')
@pytest.mark.asyncio
async def test_reference_resolution(deterministic_engine: DecisionEngine):
    candidates = ["notes.txt", "resume.pdf", "project.zip"]
    res_second = await deterministic_engine.resolve_reference(
        utterance="open the second one",
        candidate_entities=candidates,
        context_type="filesystem",
    )
    assert res_second.decision == "resume.pdf"
    assert res_second.confidence >= 0.85

    res_third = await deterministic_engine.resolve_reference(
        utterance="open the 3rd one",
        candidate_entities=candidates,
        context_type="filesystem",
    )
    assert res_third.decision == "project.zip"
    assert res_third.confidence >= 0.85


# 5. Ordinal Resolution
@pytest.mark.asyncio
async def test_ordinal_resolution(deterministic_engine: DecisionEngine):
    items = ["folder_alpha", "folder_beta", "folder_gamma", "folder_delta"]
    res = await deterministic_engine.resolve_reference(
        utterance="open the first folder",
        candidate_entities=items,
        context_type="filesystem",
    )
    assert res.decision == "folder_alpha"

    res_last = await deterministic_engine.resolve_reference(
        utterance="open the last one",
        candidate_entities=items,
        context_type="filesystem",
    )
    assert res_last.decision == "folder_delta"


# 6. Ambiguity Gate
@pytest.mark.asyncio
async def test_ambiguity_gate(deterministic_engine: DecisionEngine):
    ambiguous_res = await deterministic_engine.is_ambiguous(
        utterance="open that",
        context_summary="3 open windows, 5 browser tabs, 10 desktop folders",
    )
    assert ambiguous_res.decision is True

    clear_res = await deterministic_engine.is_ambiguous(
        utterance="open the Music folder",
        context_summary="File Explorer",
    )
    assert clear_res.decision is False


# 7. Yes/No Semantic Verification
@pytest.mark.asyncio
async def test_semantic_verification(deterministic_engine: DecisionEngine):
    verify_pass = await deterministic_engine.semantic_verify(
        expected_goal="open Music folder",
        observed_evidence="File Explorer window open at C:/Users/Music",
    )
    assert verify_pass.decision is True
    assert verify_pass.confidence >= 0.85

    verify_fail = await deterministic_engine.semantic_verify(
        expected_goal="open Music folder",
        observed_evidence="Google Chrome at google.com/search?q=music",
    )
    assert verify_fail.decision is False


# 8. Confidence Threshold
def test_confidence_threshold():
    high_conf = DecisionResult(decision="test", confidence=0.88, available=True)
    assert high_conf.is_confident is True

    low_conf = DecisionResult(decision="test", confidence=0.72, available=True)
    assert low_conf.is_confident is False

    unavail = DecisionResult(decision="test", confidence=0.95, available=False)
    assert unavail.is_confident is False


# 9. Fallback When Laya Unavailable
@pytest.mark.asyncio
async def test_fallback_when_laya_unavailable(fallback_engine: LayaDecisionEngine):
    assert fallback_engine.status == "LAYA_UNAVAILABLE"
    res = await fallback_engine.choice(
        context="some context",
        question="Which domain?",
        options=["filesystem", "browser"],
    )
    assert res.available is False
    assert res.decision == "filesystem"  # safe default
    assert res.confidence == 0.0


# 10. Latency Tracking & Live/Resident Engine
@pytest.mark.asyncio
async def test_laya_resident_engine():
    engine = get_decision_engine()
    assert isinstance(engine, DecisionEngine)
    res = await engine.choice(
        context="User: how many files are in music",
        question="Which domain does this request belong to?",
        options=["filesystem", "browser", "application", "messaging"],
    )
    assert res.decision in ["filesystem", "browser", "application", "messaging"]
    assert res.latency_ms >= 0.0
