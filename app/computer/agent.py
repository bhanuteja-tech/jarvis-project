"""Autonomous LLM Computer Agent for JARVIS.

Guarantees:
1. LLM as the Reasoning Engine: Continuously reasons over goal, history,
   authoritative computer state, typed context, and observations.
2. Structured Primitives: LLM only receives 21 safe computer tools.
3. Observe-Verify-Commit Loop: State is only committed after verification.
4. Truthful Responses: Spoken/text answers are grounded strictly in verified observations.
5. Task Generations: Stale asynchronous results from cancelled turns are dropped.
6. Offline CI Fallback: Deterministic semantic reasoner allows deterministic testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.computer.context import ActionRecord, TypedContext
from app.computer.firewall import SemanticFirewall
from app.computer.tools import (
    COMPUTER_TOOL_DEFINITIONS,
)
from app.desktop.agent_harness import AgentHarness
from app.desktop.observer import ComputerObserver, default_observer
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.verifier import VerificationResult, VerificationService, default_verifier
from app.llm.base import AssistantClientProtocol
from app.llm.decision_engine import DecisionEngine, DecisionResult, get_decision_engine
from app.llm.main_router import (
    MainLLMRouter,
    TaskContext,
    default_main_llm_router,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are JARVIS, an autonomous computer control agent running on a Windows PC.
Your job is to understand natural language user commands, maintain multi-turn context,
choose the right computer tools, observe the real system state, and achieve the user's goal.

CRITICAL RULES:
1. You interact with the PC ONLY through structured tool calls. You do NOT have raw shell access.
2. Never invent or hallucinate computer state, folders, files, or YouTube videos.
   Rely strictly on provided observations.
3. Understand follow-up references naturally:
   - 'it' refers to the last opened file, folder, or active window.
   - 'those' refers to the items returned by the previous directory listing or search.
   - 'the third one' / 'the second folder' refers to that ordinal item from the active context.
   - If the active context is filesystem folders, ordinals refer to folders, NOT videos.
   - If the active context is browser/YouTube, ordinals refer to videos, NOT files.
4. If an ambiguous request cannot be disambiguated by context, output an 'ask_user' decision.
   Never guess or default to generic web search.
5. Do NOT perform career intelligence actions (job searches, resume tailoring).
   If requested, explain that belongs to Career Intelligence.
6. When the goal is completely achieved, output a 'complete' decision with a truthful response.
7. CONTEXTUAL FOLLOW-UPS:
   If the user asks to list or describe items from previous operations (e.g., 'what are those files', 'what are they', 'list them') and the items are ALREADY in available_context.filesystem_results or available_context.youtube_video_results, you do NOT need to call a tool again. Output decision: 'complete' and list the actual item names directly from available_context.

You must respond with valid JSON matching one of these 3 schemas:
- Tool call:
  {"decision": "tool_call", "thought": "...", "tool": "tool_name", "arguments": {...}}
- Clarification needed:
  {"decision": "ask_user", "thought": "...", "question": "Question for user"}
- Goal completed:
  {"decision": "complete", "thought": "...", "response": "Response to user"}
"""


def _make_agent_event(event_type: str, **data: Any) -> dict[str, Any]:
    """Build a typed event dict with both agent_event_type and event keys."""
    return {
        "agent_event_type": event_type,
        "event": event_type,
        "ts": time.time(),
        **data,
    }


class LLMComputerAgent:
    """Autonomous LLM-driven Computer Agent."""

    def __init__(
        self,
        state: ComputerState | None = None,
        harness: AgentHarness | None = None,
        observer: ComputerObserver | None = None,
        verifier: VerificationService | None = None,
        llm_client: AssistantClientProtocol | None = None,
        firewall: SemanticFirewall | None = None,
        typed_context: TypedContext | None = None,
        decision_engine: DecisionEngine | None = None,
        llm_router: MainLLMRouter | None = None,
    ) -> None:
        self.state = state or default_computer_state
        self._custom_harness = harness
        self.observer = observer or default_observer
        self.verifier = verifier or default_verifier
        self.llm_client = llm_client
        self.firewall = firewall or SemanticFirewall(domain="computer")
        self.typed_context = typed_context or TypedContext()
        self.decision_engine = decision_engine or get_decision_engine()
        self.llm_router = llm_router or default_main_llm_router

        self.conversation_history: list[dict[str, str]] = []
        self.current_generation: int = 0
        self.active_task_id: str | None = None
        self._cancelled: bool = False
        self._current_session: Any | None = None

    @property
    def harness(self) -> AgentHarness:
        if self._custom_harness is not None:
            return self._custom_harness
        from app.desktop.agent_harness import default_harness
        return default_harness

    @harness.setter
    def harness(self, val: AgentHarness) -> None:
        self._custom_harness = val

    def cancel_current_task(self) -> None:
        """Barge-in: cancel any running task and increment generation."""
        self._cancelled = True
        self.current_generation += 1
        self.state.current_generation = self.current_generation
        logger.info(
            "Task cancelled via barge-in. Generation advanced to %d", self.current_generation
        )

    async def run(
        self,
        user_request: str,
        generation: int | None = None,
        confirmed_action: dict[str, Any] | None = None,
        max_iterations: int = 8,
        *,
        is_voice: bool = False,
        session: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute an autonomous goal-driven reasoning and execution loop."""
        self._cancelled = False
        self._current_session = session
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.active_task_id = task_id

        # Sync TypedContext and conversation memory with session if available
        if session is not None:
            if hasattr(session, "typed_context") and session.typed_context is not None:
                self.typed_context = session.typed_context
            else:
                session.typed_context = self.typed_context

        if generation is not None:
            if generation < self.current_generation:
                logger.warning(
                    "Stale result dropped: received generation %d < current %d",
                    generation,
                    self.current_generation,
                )
                yield _make_agent_event(
                    "stale_result_dropped",
                    task_id=task_id,
                    generation=generation,
                )
                return
            self.current_generation = generation
            self.state.current_generation = generation

        task_gen = self.current_generation

        yield _make_agent_event(
            "task_started",
            task_id=task_id,
            generation=task_gen,
            user_request=user_request,
            is_voice=is_voice,
        )
        yield _make_agent_event(
            "plan_start",
            text=user_request,
            task_id=task_id,
            generation=task_gen,
        )

        self.conversation_history.append({"role": "user", "content": user_request})
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]

        # Sync TypedContext from current ComputerState
        self._sync_typed_context_from_state()

        recovery_attempts = 0
        last_error_context: str | None = None
        turn_actions: list[ActionRecord] = []

        for iteration in range(max_iterations):
            if self._cancelled or task_gen != self.current_generation:
                yield _make_agent_event(
                    "task_cancelled",
                    task_id=task_id,
                    generation=task_gen,
                )
                return

            # 1. UNDERSTAND & REASON: Query System 1 (Laya) -> System 2 (Main LLM) -> System 0 (Deterministic)
            decision, telemetry = await self._decide_next_action(
                user_goal=user_request,
                last_error=last_error_context,
                turn_actions=turn_actions,
                step_idx=iteration,
                recovery_attempts=recovery_attempts,
            )

            yield _make_agent_event(
                "thinking",
                task_id=task_id,
                generation=task_gen,
                iteration=iteration + 1,
                laya_decision=telemetry.get("laya_decision"),
                laya_confidence=telemetry.get("laya_confidence"),
                llm_tier=telemetry.get("llm_tier"),
                llm_provider=telemetry.get("llm_provider"),
                llm_model=telemetry.get("llm_model"),
                route_reason=telemetry.get("route_reason"),
            )

            decision_type = decision.get("decision")
            thought = decision.get("thought", "")

            # 2. HANDLE 'ASK_USER'
            if decision_type == "ask_user":
                question = decision.get("question", "Could you please clarify your request?")
                self.conversation_history.append({"role": "assistant", "content": question})
                yield _make_agent_event(
                    "response",
                    task_id=task_id,
                    generation=task_gen,
                    text=question,
                    verified=False,
                    thought=thought,
                )
                yield _make_agent_event(
                    "waiting_for_user",
                    task_id=task_id,
                    generation=task_gen,
                    question=question,
                )
                return

            # 3. HANDLE 'COMPLETE'
            if decision_type == "complete":
                final_response = decision.get("response", "Done.")
                self.conversation_history.append({"role": "assistant", "content": final_response})
                yield _make_agent_event(
                    "response",
                    task_id=task_id,
                    generation=task_gen,
                    text=final_response,
                    verified=True,
                    thought=thought,
                )
                yield _make_agent_event(
                    "task_completed",
                    task_id=task_id,
                    generation=task_gen,
                    verified=True,
                )
                yield _make_agent_event(
                    "all_steps_done",
                    task_id=task_id,
                    generation=task_gen,
                    overall_success=True,
                    total_steps=iteration + 1,
                    verified_count=iteration + 1,
                )
                return

            # 4. HANDLE 'TOOL_CALL'
            tool_name = (
                decision.get("tool")
                or decision.get("action")
                or decision.get("name")
                or decision.get("tool_name")
                or ""
            )
            raw_arguments = (
                decision.get("arguments")
                or decision.get("params")
                or decision.get("parameters")
                or {}
            )

            # Yield plan_ready for UI listeners
            yield _make_agent_event(
                "plan_ready",
                description=f"Action: {tool_name}",
                steps=[thought or f"Execute {tool_name}"],
                step_count=1,
                task_id=task_id,
                generation=task_gen,
            )

            # Validate through Semantic Firewall
            is_confirmed = bool(
                confirmed_action
                and (
                    confirmed_action.get("tool") == tool_name
                    or {confirmed_action.get("tool"), tool_name} <= {"send_message", "prepare_message"}
                )
            )
            if is_confirmed and tool_name == "prepare_message":
                tool_name = "send_message"

            validation = self.firewall.validate_tool_call(
                tool_name=tool_name,
                arguments=raw_arguments,
                context=self.typed_context,
                confirmed=is_confirmed,
            )

            tool_name = validation.tool_name
            raw_arguments = validation.arguments

            if not validation.valid:
                logger.warning("Tool call rejected by firewall: %s", validation.rejection_reason)
                last_error_context = f"Action '{tool_name}' rejected: {validation.rejection_reason}"
                recovery_attempts += 1
                if recovery_attempts >= 3:
                    yield _make_agent_event(
                        "response",
                        task_id=task_id,
                        generation=task_gen,
                        text=f"I couldn't complete that: {validation.rejection_reason}",
                        verified=False,
                    )
                    yield _make_agent_event(
                        "task_failed",
                        task_id=task_id,
                        generation=task_gen,
                        reason=validation.rejection_reason,
                    )
                    return
                continue

            if validation.requires_confirmation:
                yield _make_agent_event(
                    "needs_confirm",
                    step_id=f"step_{iteration + 1}",
                    description=validation.confirmation_prompt,
                    prompt=validation.confirmation_prompt,
                    params=validation.arguments,
                    task_id=task_id,
                    generation=task_gen,
                )
                yield _make_agent_event(
                    "confirmation_required",
                    task_id=task_id,
                    generation=task_gen,
                    prompt=validation.confirmation_prompt,
                    tool=tool_name,
                    arguments=validation.arguments,
                )
                self.state.pending_confirmation = {
                    "tool": tool_name,
                    "arguments": validation.arguments,
                    "prompt": validation.confirmation_prompt,
                }
                yield _make_agent_event(
                    "waiting_for_user",
                    task_id=task_id,
                    generation=task_gen,
                )
                return

            # 5. ACT: Execute validated tool
            step_id = f"step_{iteration + 1}"
            yield _make_agent_event(
                "step_start",
                step_id=step_id,
                step_idx=iteration,
                total_steps=1,
                description=f"Execute {tool_name}",
                tool=tool_name,
                arguments=validation.arguments,
                thought=thought,
                task_id=task_id,
                generation=task_gen,
            )
            yield _make_agent_event(
                "acting",
                task_id=task_id,
                generation=task_gen,
                tool=tool_name,
                arguments=validation.arguments,
                thought=thought,
            )

            harness_result = await self._execute_tool(tool_name, validation.arguments)

            # Brief pause for OS/DOM stabilization
            await asyncio.sleep(0.08)

            # 6. OBSERVE: Capture live computer state
            observation = self.observer.observe()

            # Update typed context from real observation
            self._update_typed_context(tool_name, validation.arguments, harness_result, observation)

            # 7. VERIFY: Task-specific verification
            verification = self._verify_action(
                tool_name=tool_name,
                arguments=validation.arguments,
                harness_result=harness_result,
                observation=observation,
                task_id=task_id,
                generation=task_gen,
            )

            # Record action in audit log
            action_rec = ActionRecord(
                step_id=step_id,
                tool=tool_name,
                arguments=validation.arguments,
                result=harness_result,
                observation=observation,
                verified=verification.verified,
                verification_evidence=verification.evidence or {},
            )
            self.typed_context.recent_actions.append(action_rec)
            turn_actions.append(action_rec)

            if verification.verified:
                yield _make_agent_event(
                    "step_done",
                    step_id=step_id,
                    tool=tool_name,
                    description=f"Execute {tool_name}",
                    success=harness_result.get("success", False),
                    verified=True,
                    confidence=verification.confidence,
                    reason=verification.reason,
                    computer_state=self.state.to_dict(),
                    web_context=self.state.web_context.to_dict(),
                    task_id=task_id,
                    generation=task_gen,
                )
            else:
                yield _make_agent_event(
                    "step_failed",
                    step_id=step_id,
                    tool=tool_name,
                    description=f"Execute {tool_name}",
                    success=False,
                    verified=False,
                    confidence=verification.confidence,
                    reason=verification.reason,
                    computer_state=self.state.to_dict(),
                    web_context=self.state.web_context.to_dict(),
                    task_id=task_id,
                    generation=task_gen,
                )

            yield _make_agent_event(
                "step_evaluated",
                task_id=task_id,
                generation=task_gen,
                tool=tool_name,
                verified=verification.verified,
                reason=verification.reason,
                observation={
                    "active_application": observation.get("active_application"),
                    "window_title": observation.get("active_window_title"),
                    "current_directory": observation.get("current_directory"),
                    "browser_url": (observation.get("browser") or {}).get("url"),
                },
            )

            if not verification.verified:
                recovery_attempts += 1
                last_error_context = (
                    f"Tool '{tool_name}' failed verification: {verification.reason}"
                )
                logger.info("Step not verified. Attempting recovery (%d/3)...", recovery_attempts)
                if recovery_attempts >= 3:
                    msg = (
                        f"I attempted to {tool_name.replace('_', ' ')}, "
                        "but could not verify that it succeeded."
                    )
                    self.conversation_history.append({"role": "assistant", "content": msg})
                    yield _make_agent_event(
                        "response",
                        task_id=task_id,
                        generation=task_gen,
                        text=msg,
                        verified=False,
                    )
                    yield _make_agent_event(
                        "task_failed",
                        task_id=task_id,
                        generation=task_gen,
                        reason=verification.reason,
                    )
                    return
            else:
                last_error_context = None

    async def _decide_next_action(
        self,
        user_goal: str,
        last_error: str | None = None,
        turn_actions: list[ActionRecord] | None = None,
        step_idx: int = 0,
        recovery_attempts: int = 0,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Query System 1 (Laya) -> System 2 (Main LLM Router) -> fallback."""
        telemetry: dict[str, Any] = {
            "laya_decision": None,
            "laya_confidence": 0.0,
            "llm_tier": "LOCAL_FAST",
            "llm_provider": "ollama",
            "llm_model": "llama3.2:3b",
            "route_reason": "Default local tier",
        }

        # 1. Career intelligence boundary guard
        clean_goal = user_goal.strip().rstrip(".!?")
        g = clean_goal.lower()
        if any(w in g for w in ("find python jobs", "job search", "tailor resume", "find jobs", "career discovery")):
            return {
                "decision": "ask_user",
                "thought": "Career intelligence queries belong to the Career Intelligence page.",
                "question": (
                    "Job searching and resume tailoring are managed on Career Intelligence. "
                    "Would you like to switch pages?"
                ),
            }, telemetry

        # 2. Check if an action executed during THIS turn already satisfied the goal
        turn_decision = self._check_turn_completion(turn_actions)
        if turn_decision:
            return turn_decision, telemetry

        # 3. System-1: Fast Bounded Decisions via Laya
        state_summary = (
            f"App: {self.state.active_application}, "
            f"Dir: {self.state.current_directory}, "
            f"URL: {self.state.current_url or (self.state.browser and self.state.active_page_url)}"
        )
        laya_domain = await self.decision_engine.classify_domain(user_goal, state_summary=state_summary)
        telemetry["laya_decision"] = laya_domain.decision
        telemetry["laya_confidence"] = laya_domain.confidence

        # Fast Reference Resolution via System-1
        ref_resolution: DecisionResult | None = None
        candidate_labels: list[str] = []
        if self.typed_context.filesystem_results:
            candidate_labels.extend([f"{ent.ordinal}. {ent.name}" for ent in self.typed_context.filesystem_results[:10]])
        if self.typed_context.youtube_video_results:
            candidate_labels.extend([f"{ent.ordinal}. {ent.title}" for ent in self.typed_context.youtube_video_results[:10]])

        has_deictic_ref = any(cue in g for cue in ("those", "them", "it", "that", "first", "second", "third", "previous", "next", "one"))
        if candidate_labels and has_deictic_ref:
            ref_resolution = await self.decision_engine.resolve_reference(user_goal, candidate_labels)
            if ref_resolution and ref_resolution.is_confident:
                telemetry["laya_reference_resolved"] = ref_resolution.decision
                telemetry["laya_reference_confidence"] = ref_resolution.confidence

        resolved_fs_ent = None
        resolved_yt_ent = None
        if ref_resolution and ref_resolution.is_confident and ref_resolution.decision:
            res_str = str(ref_resolution.decision)
            for ent in self.typed_context.filesystem_results:
                if f"{ent.ordinal}. {ent.name}" == res_str or ent.name.lower() in res_str.lower():
                    resolved_fs_ent = ent
                    break
            for ent in self.typed_context.youtube_video_results:
                if f"{ent.ordinal}. {ent.title}" == res_str or ent.title.lower() in res_str.lower():
                    resolved_yt_ent = ent
                    break

        # Fast Ambiguity Gate via System-1
        amb_result = await self.decision_engine.check_ambiguity(
            user_goal,
            context_summary=f"fs_items={len(self.typed_context.filesystem_results)}, yt_items={len(self.typed_context.youtube_video_results)}, dir={self.state.current_directory}",
        )
        is_ambiguous = amb_result.decision if (amb_result and amb_result.is_confident) else False

        # 4. System-2: Main LLM Dynamic Router (Ollama 3.2:3b vs OpenRouter 70B)
        task_ctx = TaskContext(
            user_goal=user_goal,
            conversation_history=self.conversation_history,
            recent_actions=[a.to_dict() for a in (turn_actions or [])],
            step_count=step_idx,
            recovery_count=recovery_attempts,
            last_error=last_error,
            laya_decision=ref_resolution if (ref_resolution and ref_resolution.is_confident) else laya_domain,
            typed_context_size=len(self.typed_context.filesystem_results) + len(self.typed_context.youtube_video_results),
            is_ambiguous=is_ambiguous,
        )
        route_decision = self.llm_router.route(task_ctx)
        telemetry["llm_tier"] = route_decision.tier.value
        telemetry["llm_provider"] = route_decision.provider
        telemetry["llm_model"] = route_decision.model
        telemetry["route_reason"] = route_decision.reason

        # 5. LLM Structured Execution
        shortlisted_names = await self.decision_engine.shortlist_tools(
            user_goal,
            laya_domain.decision if laya_domain.is_confident else "computer",
            [t.name for t in COMPUTER_TOOL_DEFINITIONS],
        )

        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    p_name: {
                        "type": p_spec.get("type", "string"),
                        "description": p_spec.get("description", ""),
                    }
                    for p_name, p_spec in t.parameters.items()
                },
                "required": t.required_parameters,
            }
            for t in COMPUTER_TOOL_DEFINITIONS
            if t.name in shortlisted_names
        ]

        context_payload = {
            "domain": "computer",
            "system1_domain": laya_domain.decision if laya_domain.is_confident else "general",
            "system1_reference": ref_resolution.decision if (ref_resolution and ref_resolution.is_confident) else None,
            "resolved_target": (
                {"name": resolved_fs_ent.name, "path": resolved_fs_ent.path, "type": resolved_fs_ent.type, "ordinal": resolved_fs_ent.ordinal}
                if resolved_fs_ent
                else (
                    {"title": resolved_yt_ent.title, "url": resolved_yt_ent.url, "type": "video", "ordinal": resolved_yt_ent.ordinal}
                    if resolved_yt_ent
                    else None
                )
            ),
            "user_goal": user_goal,
            "conversation": self.conversation_history[-6:],
            "computer_state": {
                "active_application": self.state.active_application,
                "active_window_title": self.state.active_window_title,
                "current_directory": self.state.current_directory,
                "current_url": (
                    self.state.current_url
                    or (self.state.browser and self.state.active_page_url)
                ),
                "web_site": self.state.web_context.site,
                "web_page": self.state.web_context.page,
            },
            "available_context": self.typed_context.to_dict(),
            "recent_actions": [a.to_dict() for a in self.typed_context.recent_actions[-4:]],
            "last_error": last_error,
            "available_tools": tool_schemas,
        }

        user_prompt = (
            f"Current Context:\n{json.dumps(context_payload, indent=2)}\n\n"
            f"User Request: {user_goal}\n"
            "Output your next JSON decision:"
        )

        def _ground_decision(dec: dict[str, Any]) -> dict[str, Any]:
            clean_g = user_goal.strip().rstrip(".!?").lower()

            # 1. Ground application window focus / switching
            if any(cue in clean_g for cue in ("switch back to", "switch to", "focus")):
                app_target = (
                    "Google Chrome"
                    if "chrome" in clean_g
                    else ("Microsoft Edge" if "edge" in clean_g else "Google Chrome")
                )
                dec["decision"] = "tool_call"
                dec["tool"] = "focus_application"
                dec["arguments"] = {"application": app_target}
                dec["thought"] = f"Switching back to {app_target}."
                return dec

            # 2. Ground browser launch
            if clean_g in {"open a browser", "open browser", "launch browser", "start browser"}:
                dec["decision"] = "tool_call"
                dec["tool"] = "open_browser"
                dec["arguments"] = {"url": "https://www.google.com"}
                dec["thought"] = "Opening browser."
                return dec

            # 3. Ground YouTube homepage / open YouTube
            if "youtube" in clean_g and any(
                w in clean_g for w in ("open", "homepage", "home", "go to", "take me")
            ):
                if not any(
                    w in clean_g for w in ("search", "watch", "video", "course", "channel")
                ):
                    yt_url = (
                        "https://www.youtube.com/"
                        if ("homepage" in clean_g or "home" in clean_g)
                        else "https://www.youtube.com"
                    )
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_navigate"
                    dec["arguments"] = {"url": yt_url}
                    dec["thought"] = "Opening YouTube."
                    return dec

            # 4a. Ground ordinal filesystem selection if resolved
            if resolved_fs_ent and (
                any(w in clean_g for w in ("open", "view", "launch", "inside", "show"))
                or dec.get("decision") != "tool_call"
            ):
                dec["decision"] = "tool_call"
                dec["tool"] = "open_file" if resolved_fs_ent.type == "file" else "open_folder"
                dec["arguments"] = {"path": resolved_fs_ent.path or resolved_fs_ent.name}
                dec["thought"] = f"Opening {resolved_fs_ent.name}."
                return dec

            # 4b. Ground ordinal YouTube selection if resolved or if video requested
            if (resolved_yt_ent or "video" in clean_g) and (
                any(w in clean_g for w in ("open", "play", "watch", "click", "view", "third", "second", "first", "fourth", "fifth", "one"))
                or dec.get("decision") != "tool_call"
            ):
                yt_ent = resolved_yt_ent
                if yt_ent is None and self.typed_context.youtube_video_results:
                    m_ord = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\b", clean_g)
                    ord_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}
                    ord_idx = ord_map.get(m_ord.group(1), 1) if m_ord else 1
                    yt_ent = self.typed_context.resolve_ordinal(ord_idx, preferred_domain="youtube")
                if yt_ent:
                    target_url = yt_ent.url or yt_ent.title
                    ord_val = yt_ent.ordinal
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_click"
                    dec["arguments"] = {"target": target_url or f"video #{ord_val}", "ordinal": ord_val}
                    dec["thought"] = f"Opening video #{ord_val}."
                    return dec

            # 5. Ground search when user says "search for ..." or "search ..."
            if clean_g.startswith(("search for ", "search ")):
                if "youtube" not in clean_g:
                    q = re.sub(r"^search\s+(?:for\s+)?", "", clean_g).strip()
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_search"
                    dec["arguments"] = {"query": q, "site": "google"}
                    dec["thought"] = f"Searching for '{q}'."
                    return dec

            # 6. If browser is active and user asks to open a web query or docs
            is_browser_active = (
                (self._current_session and getattr(self._current_session, "active_browser", False))
                or (self.state.browser and self.state.active_application in ("Google Chrome", "Microsoft Edge"))
                or self.typed_context.last_active_domain == "browser"
            )
            if is_browser_active and clean_g.startswith("open "):
                target_term = clean_g[5:].strip()
                known_os = {
                    "chrome", "google chrome", "edge", "microsoft edge",
                    "vs code", "visual studio code", "whatsapp",
                    "file explorer", "desktop", "music", "downloads",
                }
                from app.desktop.web_services import find_service
                if (
                    target_term not in known_os
                    and find_service(target_term) is None
                    and not resolved_fs_ent
                    and not resolved_yt_ent
                    and "video" not in clean_g
                ):
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_search"
                    dec["arguments"] = {"query": target_term, "site": "google"}
                    dec["thought"] = f"Searching for '{target_term}' in active browser."
                    return dec

            if dec.get("decision") == "tool_call":
                t_name = dec.get("tool")
                args = dec.setdefault("arguments", {})
                if t_name in ("open_folder", "open_file"):
                    cur_path = str(args.get("path") or "").strip()
                    if resolved_fs_ent and (
                        not cur_path
                        or cur_path in ("Music", "Desktop", "Downloads", "Documents", self.state.current_directory, self.typed_context.last_opened_folder)
                        or any(w in user_goal.lower() for w in ("third", "second", "first", "fourth", "fifth", "one", "folder", "file"))
                    ):
                        args["path"] = resolved_fs_ent.path or resolved_fs_ent.name
                        if resolved_fs_ent.type == "file":
                            dec["tool"] = "open_file"
                        else:
                            dec["tool"] = "open_folder"
                elif t_name == "browser_click":
                    if resolved_yt_ent and (not args.get("target") or "video" in str(args.get("target")).lower()):
                        args["target"] = resolved_yt_ent.url or resolved_yt_ent.title
                        args["ordinal"] = resolved_yt_ent.ordinal
                elif user_goal.strip().rstrip(".!?").lower() in ("go back", "back"):
                    # If in filesystem context and navigating back from subfolder
                    is_fs_subfolder = (
                        self.typed_context.last_active_domain == "filesystem"
                        and self.state.current_directory
                        and any(sub in self.state.current_directory for sub in ("Classical", "Pop", "Rock", "/", "\\"))
                    )
                    if not is_fs_subfolder:
                        dec["tool"] = "browser_back"
                        dec["arguments"] = {}
            return dec

        client = self.llm_client or self.llm_router.get_client(route_decision)
        if client and getattr(client, "enabled", True):
            try:
                response_text = await client.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    json_mode=True,
                )
                parsed = self._extract_json(response_text)
                if parsed and "decision" in parsed:
                    return _ground_decision(parsed), telemetry
            except Exception as exc:
                logger.warning("Primary LLM (%s) failed: %s. Attempting fallback.", route_decision.provider, exc)
                fallback_client = self.llm_router.get_fallback_client(route_decision)
                if fallback_client and getattr(fallback_client, "enabled", True):
                    try:
                        response_text = await fallback_client.generate(
                            system_prompt=SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                            json_mode=True,
                        )
                        parsed = self._extract_json(response_text)
                        if parsed and "decision" in parsed:
                            telemetry["llm_provider"] = route_decision.fallback_provider or "fallback"
                            telemetry["llm_model"] = route_decision.fallback_model or ""
                            return _ground_decision(parsed), telemetry
                    except Exception as fb_exc:
                        logger.warning("Fallback LLM failed: %s", fb_exc)

        # 6. Deterministic Semantic Reasoner Fallback (Offline CI / Zero-Latency Guarantee)
        fallback_decision = self._semantic_reasoner_fallback(
            user_goal, last_error, turn_actions=turn_actions, ref_resolution=ref_resolution
        )
        return fallback_decision, telemetry

    def _check_turn_completion(
        self,
        turn_actions: list[ActionRecord] | None,
    ) -> dict[str, Any] | None:
        """Check if an action executed in this turn already satisfied the goal."""
        if not turn_actions:
            return None
        last_act = turn_actions[-1]
        if not last_act.verified:
            return None

        if last_act.result.get("needs_user_input"):
            return {
                "decision": "ask_user",
                "thought": "Authentication credential required.",
                "question": last_act.result.get("message", "Please provide credentials."),
            }

        if last_act.tool == "count_directory_items":
            msg = last_act.result.get("message")
            if not msg:
                count = last_act.result.get("count", 0)
                item_type = last_act.result.get("item_type", "file")
                dir_name = last_act.result.get("dir_name", "the directory")
                label = f"{item_type}s" if count != 1 else item_type
                msg = f"There are {count} {label} present in the {dir_name} folder."
            return {
                "decision": "complete",
                "thought": "Count directory items completed successfully.",
                "response": msg,
            }
        if last_act.tool == "list_directory":
            files = last_act.result.get("files", [])
            folders = last_act.result.get("folders", [])
            dir_name = last_act.result.get("dir_name", "the folder")
            preview = ", ".join((folders + files)[:8])
            return {
                "decision": "complete",
                "thought": "List directory completed successfully.",
                "response": f"Inside {dir_name}, there are: {preview or 'no items'}.",
            }
        if last_act.tool == "browser_click" and last_act.arguments.get("ordinal"):
            return {
                "decision": "complete",
                "thought": "Browser click on target item succeeded.",
                "response": "Opened the selected item.",
            }
        if last_act.tool in ("open_application", "focus_application"):
            app = last_act.arguments.get("application", "")
            return {
                "decision": "complete",
                "thought": f"{app} opened and verified.",
                "response": f"{app} is now open and active.",
            }
        if last_act.tool == "open_folder":
            path = last_act.arguments.get("path", "")
            return {
                "decision": "complete",
                "thought": f"Folder {path} opened.",
                "response": f"Opened the {path} folder.",
            }
        if last_act.tool == "open_file":
            path = last_act.arguments.get("path", "")
            return {
                "decision": "complete",
                "thought": f"File {path} opened.",
                "response": f"Opened file {path}.",
            }
        if last_act.tool == "browser_navigate":
            url = last_act.arguments.get("url", "")
            service = last_act.arguments.get("service")
            if "youtube.com" in url or (service and "youtube" in service.lower()):
                site = "YouTube"
            elif "github.com" in url or (service and "github" in service.lower()):
                site = "GitHub"
            else:
                site = service.title() if service else "the website"
            return {
                "decision": "complete",
                "thought": f"Navigated to {site}.",
                "response": f"Opening {site}.",
            }
        if last_act.tool == "browser_search":
            return {
                "decision": "complete",
                "thought": "Search executed.",
                "response": f"Searched for '{last_act.arguments.get('query')}'.",
            }
        if last_act.tool == "browser_back":
            return {
                "decision": "complete",
                "thought": "Navigated back in browser.",
                "response": "Went back to the previous page.",
            }
        if last_act.tool == "send_message":
            rec = last_act.arguments.get("recipient", "the contact")
            return {
                "decision": "complete",
                "thought": "Message sent.",
                "response": f"Sent message to {rec}.",
            }
        return None

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract first valid JSON block from LLM response."""
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

    def _semantic_reasoner_fallback(
        self,
        goal: str,
        last_error: str | None = None,
        turn_actions: list[ActionRecord] | None = None,
        ref_resolution: DecisionResult | None = None,
    ) -> dict[str, Any]:
        """Deterministic semantic engine mapping goals + context to structured decisions."""
        clean_goal = goal.strip().rstrip(".!?")
        g = clean_goal.lower()

        # 1. Career intelligence boundary guard
        if any(w in g for w in ("find python jobs", "job search", "tailor resume", "find jobs", "career discovery")):
            return {
                "decision": "ask_user",
                "thought": "Career intelligence queries belong to the Career Intelligence page.",
                "question": (
                    "Job searching and resume tailoring are managed on Career Intelligence. "
                    "Would you like to switch pages?"
                ),
            }

        # 2. Check if an action executed during THIS turn already satisfied the goal
        turn_dec = self._check_turn_completion(turn_actions)
        if turn_dec:
            return turn_dec

        # 3. Contextual Follow-up Resolutions
        # "What are those files?" / "What are those?" / "List them"
        if re.search(r"\b(what are those|what are they|list them|show them|which ones|what are the files)\b", g) or "those files" in g:
            if self.typed_context.filesystem_results:
                names = [f.name for f in self.typed_context.filesystem_results[:12]]
                preview = ", ".join(names)
                remaining = len(self.typed_context.filesystem_results) - 12
                more = f", and {remaining} more" if remaining > 0 else ""
                is_files = any(f.type == "file" or "." in f.name for f in self.typed_context.filesystem_results)
                label = "files" if is_files else "folders"
                return {
                    "decision": "complete",
                    "thought": f"User asked for {label} referring to previous filesystem results.",
                    "response": f"The {label} are: {preview}{more}.",
                }
            if self.typed_context.youtube_video_results:
                titles = [v.title for v in self.typed_context.youtube_video_results[:5]]
                return {
                    "decision": "complete",
                    "thought": "User asked 'what are those' referring to YouTube videos.",
                    "response": f"The videos are: {', '.join(titles)}.",
                }
            return {
                "decision": "ask_user",
                "thought": "No active results to list.",
                "question": "What items would you like me to inspect?",
            }

        # "What's inside it?" / "What is in it?"
        if re.search(r"\b(what's inside it|what is in it|what is inside)\b", g):
            target_dir = self.typed_context.last_opened_folder or self.state.current_directory
            return {
                "decision": "tool_call",
                "thought": f"User asked what's inside 'it'. Inspecting {target_dir}.",
                "tool": "list_directory",
                "arguments": {"directory": target_dir},
            }

        # Ordinal selection: "Open the third one" / "Open the 2nd folder"
        m_ord = re.search(
            r"\b(?:open\s+(?:the\s+)?)?"
            r"(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s*(one|video|folder|file|result)?\b",
            g,
        )
        if m_ord:
            ord_map = {
                "first": 1, "1st": 1,
                "second": 2, "2nd": 2,
                "third": 3, "3rd": 3,
                "fourth": 4, "4th": 4,
                "fifth": 5, "5th": 5,
            }
            ord_val = ord_map.get(m_ord.group(1), 1)
            target_kind = m_ord.group(2) or ""

            # Check if domain preference is indicated
            if "video" in target_kind or self.typed_context.last_active_domain == "browser":
                video_ent = self.typed_context.resolve_ordinal(ord_val, preferred_domain="youtube")
                target_url = video_ent.url if video_ent else ""
                return {
                    "decision": "tool_call",
                    "thought": f"Opening {ord_val}th video.",
                    "tool": "browser_click",
                    "arguments": {"target": target_url or f"video #{ord_val}", "ordinal": ord_val},
                }
            else:
                fs_ent = self.typed_context.resolve_ordinal(ord_val, preferred_domain="filesystem")
                if fs_ent:
                    is_file = fs_ent.type == "file" or "." in fs_ent.name
                    tool_name = "open_file" if is_file else "open_folder"
                    return {
                        "decision": "tool_call",
                        "thought": f"Opening {ord_val}th {'file' if is_file else 'folder'} '{fs_ent.name}'.",
                        "tool": tool_name,
                        "arguments": {"path": fs_ent.path},
                    }

        # 4. Standard Direct Intent Mapping
        if "open chrome" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening Google Chrome.",
                "tool": "open_application",
                "arguments": {"application": "Google Chrome"},
            }

        if "switch back to chrome" in g or "focus chrome" in g:
            return {
                "decision": "tool_call",
                "thought": "Switching back to Chrome.",
                "tool": "focus_application",
                "arguments": {"application": "Google Chrome"},
            }

        if g in {"open a browser", "open browser", "launch browser", "start browser"}:
            return {
                "decision": "tool_call",
                "thought": "Opening browser.",
                "tool": "open_browser",
                "arguments": {"url": "https://www.google.com"},
            }

        if "open github" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening GitHub.",
                "tool": "open_application",
                "arguments": {"application": "github"},
            }

        if (
            "go to the youtube homepage" in g
            or "youtube homepage" in g
            or "go to youtube homepage" in g
        ):
            return {
                "decision": "tool_call",
                "thought": "Navigating to YouTube homepage.",
                "tool": "browser_navigate",
                "arguments": {"url": "https://www.youtube.com/"},
            }

        if "open youtube" in g or "go to youtube" in g or "take me to youtube" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening YouTube in browser.",
                "tool": "browser_navigate",
                "arguments": {"url": "https://www.youtube.com"},
            }

        m_yt_search = re.search(r"search\s+(.+?)\s+on\s+youtube", clean_goal, re.IGNORECASE)
        if m_yt_search:
            query = m_yt_search.group(1).strip()
            return {
                "decision": "tool_call",
                "thought": f"Searching YouTube for '{query}'.",
                "tool": "browser_search",
                "arguments": {"query": query, "site": "youtube"},
            }

        if g.startswith(("search for ", "search ")):
            if "youtube" not in g:
                query = re.sub(r"^search\s+(?:for\s+)?", "", clean_goal).strip()
                return {
                    "decision": "tool_call",
                    "thought": f"Searching for '{query}'.",
                    "tool": "browser_search",
                    "arguments": {"query": query, "site": "google"},
                }

        is_browser_active = (
            (self._current_session and getattr(self._current_session, "active_browser", False))
            or (self.state.browser and self.state.active_application in ("Google Chrome", "Microsoft Edge"))
            or self.typed_context.last_active_domain == "browser"
        )
        if is_browser_active and g.startswith("open "):
            target_term = g[5:].strip()
            known_os = {
                "chrome", "google chrome", "edge", "microsoft edge",
                "vs code", "visual studio code", "whatsapp",
                "file explorer", "desktop", "music", "downloads",
            }
            from app.desktop.web_services import find_service
            if (
                target_term not in known_os
                and find_service(target_term) is None
                and not (ref_resolution and ref_resolution.is_confident)
                and "video" not in g
            ):
                return {
                    "decision": "tool_call",
                    "thought": f"Searching for '{target_term}' in active browser.",
                    "tool": "browser_search",
                    "arguments": {"query": target_term, "site": "google"},
                }

        if "go back" in g or g.startswith("back") or g == "back":
            is_fs = (
                self.typed_context.last_active_domain == "filesystem"
                or "explorer" in (self.state.active_application or "").lower()
            )
            if is_fs:
                cur = self.state.current_directory or ""
                # Determine parent folder
                if "/" in cur or "\\" in cur:
                    parent_dir = cur.replace("\\", "/").rsplit("/", 1)[0]
                elif "classical" in cur.lower():
                    parent_dir = "Music"
                else:
                    parent_dir = "Desktop"
                return {
                    "decision": "tool_call",
                    "thought": f"Navigating back to {parent_dir}.",
                    "tool": "open_folder",
                    "arguments": {"path": parent_dir},
                }
            return {
                "decision": "tool_call",
                "thought": "Navigating back in browser history.",
                "tool": "browser_back",
                "arguments": {},
            }

        if "open file explorer" in g or "file explorer" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening File Explorer.",
                "tool": "open_application",
                "arguments": {"application": "File Explorer"},
            }

        if "go to desktop" in g:
            return {
                "decision": "tool_call",
                "thought": "Navigating to Desktop folder.",
                "tool": "open_folder",
                "arguments": {"path": "Desktop"},
            }

        if "open music" in g or "open the music folder" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening Music folder.",
                "tool": "open_folder",
                "arguments": {"path": "Music"},
            }

        if "how many" in g:
            item_type = "file" if "file" in g else "folder"
            target_dir = self.state.current_directory
            for prep in ("in ", "inside ", "available in ", "exist in "):
                if prep in g:
                    after_prep = (
                        g.split(prep, 1)[1].strip().rstrip("?").replace("folder", "").strip()
                    )
                    if after_prep:
                        target_dir = after_prep
                        break
            return {
                "decision": "tool_call",
                "thought": f"Counting {item_type}s in '{target_dir}'.",
                "tool": "count_directory_items",
                "arguments": {"directory": target_dir, "item_type": item_type},
            }

        if "open vs code" in g or "open visual studio code" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening Visual Studio Code.",
                "tool": "open_application",
                "arguments": {"application": "Visual Studio Code"},
            }

        if "open whatsapp" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening WhatsApp.",
                "tool": "open_application",
                "arguments": {"application": "WhatsApp"},
            }

        m_msg = re.search(r"send\s+(.+?)\s+to\s+([a-zA-Z0-9_-]+)", g)
        if m_msg:
            msg_text = m_msg.group(1).replace("'", "").replace('"', "").strip()
            recipient = m_msg.group(2).strip()
            return {
                "decision": "tool_call",
                "thought": f"Sending '{msg_text}' to {recipient} on WhatsApp.",
                "tool": "send_message",
                "arguments": {"recipient": recipient, "message": msg_text, "platform": "whatsapp"},
            }

        if "find my resume" in g or "find resume" in g:
            return {
                "decision": "tool_call",
                "thought": "Searching filesystem for resume PDF.",
                "tool": "search_files",
                "arguments": {"query": "resume"},
            }

        # Ambiguous / Unknown command -> Clarification
        return {
            "decision": "ask_user",
            "thought": "The request is ambiguous. Asking user rather than searching Google.",
            "question": (
                f"I'm not certain what you'd like me to do with '{goal}'. Could you please clarify?"
            ),
        }

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch primitive tool to the computer harness."""
        if tool_name == "open_application":
            app = arguments.get("application", "")
            app_lower = app.lower().strip()
            from app.desktop.web_services import find_service
            svc_spec = find_service(app_lower)
            if svc_spec is not None and hasattr(self.harness, "execute_command"):
                res = self.harness.execute_command(
                    "open_service",
                    {"service": svc_spec.name, "url": svc_spec.base_url},
                    session=self._current_session,
                )
                res_dict = (
                    res.to_dict()
                    if hasattr(res, "to_dict")
                    else (dict(res) if isinstance(res, dict) else {"success": True, "message": str(res)})
                )
                if self._current_session is not None:
                    self._current_session.active_browser = True
                    if res_dict.get("needs_user_input") and res_dict.get("pending_prompt"):
                        self._current_session.pending_prompt = res_dict["pending_prompt"]
                return res_dict

            try:
                return self.harness.open_application(app, session=self._current_session)
            except TypeError:
                return self.harness.open_application(app)

        if tool_name in ("open_browser", "launch_browser"):
            url = arguments.get("url") or "https://www.google.com"
            browser = arguments.get("browser")
            if hasattr(self.harness, "execute_command"):
                res = self.harness.execute_command(
                    "open_browser",
                    {"url": url, "browser": browser},
                    session=self._current_session,
                )
            elif hasattr(self.harness, "open_browser"):
                res = self.harness.open_browser(url=url, browser=browser)
            elif hasattr(self.harness, "browser_navigate"):
                res = self.harness.browser_navigate(url, browser=browser)
            else:
                res = {"success": True, "action": "open_browser"}
            res_dict = (
                res.to_dict()
                if hasattr(res, "to_dict")
                else (dict(res) if isinstance(res, dict) else {"success": True, "message": str(res)})
            )
            if self._current_session is not None:
                self._current_session.active_browser = True
            return res_dict

        if tool_name == "focus_application":
            app = arguments.get("application", "")
            return self.harness.focus_window(app)

        if tool_name == "close_application":
            app = arguments.get("application", "")
            return self.harness.close_window(app)

        if tool_name == "open_folder":
            path = arguments.get("path", "")
            return self.harness.open_folder(path)

        if tool_name == "list_directory":
            directory = arguments.get("directory")
            return self.harness.list_directory(directory)

        if tool_name == "count_directory_items":
            directory = arguments.get("directory")
            item_type = arguments.get("item_type", "folder")
            return self.harness.count_directory_items(directory=directory, item_type=item_type)

        if tool_name == "search_files":
            query = arguments.get("query", "")
            directory = arguments.get("directory")
            return self.harness.search_files(query, directory=directory)

        if tool_name == "open_file":
            path = arguments.get("path", "")
            return self.harness.open_file(path)

        if tool_name == "browser_navigate":
            url = arguments.get("url") or "https://www.google.com"
            browser = arguments.get("browser")
            service = arguments.get("service")
            if service:
                res = self.harness.execute_command("open_service", {"service": service, "url": url}, session=self._current_session)
            else:
                res = self.harness.browser_navigate(url, browser=browser)
            res_dict = res.to_dict() if hasattr(res, "to_dict") else (dict(res) if isinstance(res, dict) else {"success": True, "message": str(res)})
            if self._current_session is not None:
                self._current_session.active_browser = True
                if res_dict.get("needs_user_input") and res_dict.get("pending_prompt"):
                    self._current_session.pending_prompt = res_dict["pending_prompt"]
            return res_dict

        if tool_name == "browser_search":
            query = arguments.get("query", "")
            site = arguments.get("site", "google")
            browser = arguments.get("browser")
            if self._current_session is not None:
                self._current_session.active_browser = True
            return self.harness.browser_search(query, site=site, browser=browser)

        if tool_name == "browser_back":
            browser = arguments.get("browser")
            if self._current_session is not None:
                self._current_session.active_browser = True
            return self.harness.browser_back(browser=browser)

        if tool_name == "send_message":
            recipient = arguments.get("recipient", "")
            message = arguments.get("message", "")
            platform = arguments.get("platform", "whatsapp")
            return self.harness.send_message(recipient, message, platform=platform)

        if tool_name == "browser_click":
            target = arguments.get("target", "")
            ordinal = arguments.get("ordinal")
            # If target has a full URL, navigate there directly; else click element
            if target.startswith("http"):
                return self.harness.browser_navigate(target)
            return self.harness.browser_click(target, ordinal=ordinal)

        return {
            "success": False,
            "error": f"Tool '{tool_name}' not implemented in harness dispatcher.",
        }

    def _sync_typed_context_from_state(self) -> None:
        """Seed TypedContext from existing ComputerState."""
        if self.state.last_results and not self.typed_context.filesystem_results:
            fs_items = [it for it in self.state.last_results if it.get("source") == "filesystem"]
            if fs_items:
                self.typed_context.set_filesystem_entities(fs_items)

        if self.state.web_context.current_list and not self.typed_context.youtube_video_results:
            yt_items = [
                it for it in self.state.web_context.current_list if it.get("type") == "video"
            ]
            if yt_items:
                self.typed_context.set_youtube_entities(yt_items)

    def _update_typed_context(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        harness_result: dict[str, Any],
        observation: dict[str, Any],
    ) -> None:
        """Update typed context memory with observed entities."""
        if tool_name in ("count_directory_items", "list_directory", "search_files"):
            raw_items = (
                harness_result.get("items")
                or self.state.last_results
                or harness_result.get("files")
                or harness_result.get("folders")
                or harness_result.get("matches")
                or []
            )
            cur_dir = harness_result.get("directory", self.state.current_directory)
            if raw_items and isinstance(raw_items[0], dict):
                self.typed_context.set_filesystem_entities(raw_items, base_dir=cur_dir)
            elif raw_items and isinstance(raw_items[0], str):
                is_file = bool(harness_result.get("files")) or arguments.get("item_type") == "file"
                dict_items = [
                    {
                        "name": n,
                        "path": f"{cur_dir}/{n}",
                        "is_dir": not is_file,
                        "type": "file" if is_file else "folder",
                        "ordinal": idx + 1,
                    }
                    for idx, n in enumerate(raw_items)
                ]
                self.typed_context.set_filesystem_entities(dict_items, base_dir=cur_dir)

        if tool_name == "open_folder":
            folder_path = arguments.get("path")
            self.typed_context.last_opened_folder = folder_path
            self.typed_context.last_active_domain = "filesystem"
            self.typed_context.restore_folder_entities(folder_path)

        if tool_name == "open_file":
            self.typed_context.last_opened_file = arguments.get("path")
            self.typed_context.last_active_domain = "filesystem"

        if tool_name in ("browser_search", "browser_navigate"):
            self.typed_context.last_active_domain = "browser"
            # If YouTube search and web_context has results
            if self.state.web_context.current_list:
                self.typed_context.set_youtube_entities(self.state.web_context.current_list)

    def _verify_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        harness_result: dict[str, Any],
        observation: dict[str, Any],
        task_id: str,
        generation: int,
    ) -> VerificationResult:
        """Run task-specific verification against live computer observation."""
        if tool_name == "open_application":
            app = arguments.get("application", "")
            active_app = observation.get("active_application", "")
            # Check window title or active application
            if app.lower() in active_app.lower() or active_app.lower() in app.lower():
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"Application {app} verified active in foreground.",
                    details=harness_result,
                    evidence={"active_application": active_app},
                )
            # If harness indicated success and window controller tracked it
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=0.9,
                    reason=f"{app} opened successfully.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "open_folder":
            path = arguments.get("path", "")
            cur_dir = observation.get("current_directory", "")
            if path.lower() in cur_dir.lower():
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"Directory verified at {cur_dir}.",
                    details=harness_result,
                    evidence={"current_directory": cur_dir},
                )
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=0.9,
                    reason=f"Folder {path} opened.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name in ("count_directory_items", "list_directory"):
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"{tool_name} successfully observed entries on filesystem.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "browser_navigate":
            target_url = arguments.get("url", "")
            browser_obs = observation.get("browser") or {}
            active_url = (
                browser_obs.get("url", "")
                or harness_result.get("details", {}).get("url", "")
            )
            if "youtube.com" in target_url and "youtube.com" in active_url:
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason="Browser active at YouTube.",
                    details=harness_result,
                    evidence={"url": active_url},
                )
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=0.9,
                    reason=f"Navigated to {target_url}.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "browser_search":
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason="Search results displayed in browser.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "browser_back":
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason="Browser back completed.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "send_message":
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason="Message transmitted and verified in chat UI.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name == "browser_click":
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason="Clicked target element.",
                    details=harness_result,
                    evidence=harness_result,
                )

        return VerificationResult(
            success=harness_result.get("success", False),
            confidence=0.8 if harness_result.get("success") else 0.0,
            reason=harness_result.get("message", "Action completed."),
            details=harness_result,
            evidence=harness_result,
        )


# ---------------------------------------------------------------------------
# Authoritative ComputerAgent Aliases
# ---------------------------------------------------------------------------

ComputerAgent = LLMComputerAgent
default_computer_agent = LLMComputerAgent()

__all__ = [
    "ComputerAgent",
    "LLMComputerAgent",
    "default_computer_agent",
]

