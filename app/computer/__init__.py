"""Autonomous LLM Computer Agent package for JARVIS.

This package implements the autonomous reasoning, tool selection, observation,
and verification loop for computer control tasks, strictly separated from
the Career Intelligence pipeline.

Architecture:
    LLMComputerAgent         → Autonomous reasoning engine & agent loop
    TypedContext             → Structured entity memory (files, windows, DOM videos)
    SemanticFirewall         → Security & domain isolation firewall
    ComputerToolDefinition   → 21 structured computer tool schemas
    ComputerAgent            → Execution harness & WebSocket event bridge
    WebContextTracker        → YouTube/site hierarchical context
    ComputerIntentExtractor  → Structured intent extractor
    ReferenceResolver        → Pronoun & ordinal resolver
    SemanticTaskPlanner      → Deterministic step builder
    TruthfulResponseGenerator → Verified spoken response builder
"""

from __future__ import annotations

from app.computer.agent import LLMComputerAgent
from app.computer.context import (
    ActionRecord,
    BrowserResultEntity,
    BrowserTabEntity,
    FileSystemEntity,
    TypedContext,
    WindowEntity,
    YouTubeVideoEntity,
)
from app.computer.executor import ComputerAgent, default_computer_agent
from app.computer.firewall import SemanticFirewall, ToolValidationResult
from app.computer.intent_extractor import ComputerIntentExtractor, default_extractor
from app.computer.reference_resolver import ReferenceResolver, default_resolver
from app.computer.response_generator import TruthfulResponseGenerator, default_response_generator
from app.computer.semantic_planner import SemanticTaskPlanner, default_planner
from app.computer.tools import COMPUTER_TOOL_DEFINITIONS, COMPUTER_TOOLS_BY_NAME
from app.computer.web_context_tracker import WebContextTracker, default_web_context_tracker

__all__ = [
    "LLMComputerAgent",
    "TypedContext",
    "FileSystemEntity",
    "YouTubeVideoEntity",
    "BrowserResultEntity",
    "WindowEntity",
    "BrowserTabEntity",
    "ActionRecord",
    "SemanticFirewall",
    "ToolValidationResult",
    "COMPUTER_TOOL_DEFINITIONS",
    "COMPUTER_TOOLS_BY_NAME",
    "ComputerAgent",
    "default_computer_agent",
    "ComputerIntentExtractor",
    "default_extractor",
    "ReferenceResolver",
    "default_resolver",
    "WebContextTracker",
    "default_web_context_tracker",
    "SemanticTaskPlanner",
    "default_planner",
    "TruthfulResponseGenerator",
    "default_response_generator",
]
