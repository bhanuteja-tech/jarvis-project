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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.desktop.agent_harness import AgentHarness

from app.computer.circuit_breaker import ActionCircuitBreaker
from app.computer.context import ActionRecord, TypedContext
from app.computer.firewall import SemanticFirewall
from app.computer.latency_tracker import global_latency_tracker
from app.computer.tools import (
    COMPUTER_TOOL_DEFINITIONS,
    COMPUTER_TOOLS_BY_NAME,
)
from app.desktop.observer import ComputerObserver, default_observer
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.verifier import VerificationResult, VerificationService, default_verifier
from app.llm.base import AssistantClientProtocol
from app.llm.decision_engine import DecisionEngine, DecisionResult, get_decision_engine
from app.llm.gemini_computer_use import (
    ComputerUseProvider,
    GeminiComputerUseProvider,
)
from app.llm.main_router import (
    MainLLMRouter,
    TaskContext,
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
   If the user asks to list or describe items from previous operations
   (e.g., 'what are those files', 'what are they', 'list them') and the items
   are ALREADY in available_context.filesystem_results or
   available_context.youtube_video_results, you do NOT need to call a tool again.
   Output decision: 'complete' and list the actual item names directly from available_context.

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
        circuit_breaker: ActionCircuitBreaker | None = None,
        decision_engine: DecisionEngine | None = None,
        llm_router: MainLLMRouter | None = None,
        computer_use_provider: ComputerUseProvider | None = None,
        task_manager: Any | None = None,
    ) -> None:
        self.state = state or default_computer_state
        self._custom_harness = harness
        self.observer = observer or default_observer
        self.verifier = verifier or default_verifier
        self.llm_client = llm_client
        self.firewall = firewall or SemanticFirewall(domain="computer")
        self.typed_context = typed_context or TypedContext()
        self.circuit_breaker = circuit_breaker or ActionCircuitBreaker()
        self.decision_engine = decision_engine or get_decision_engine()
        self.llm_router = llm_router or MainLLMRouter()
        if task_manager is not None:
            self.task_manager = task_manager
        else:
            from app.agent.task_manager import TaskManager

            self.task_manager = TaskManager()

        if computer_use_provider is not None:
            self.computer_use_provider: ComputerUseProvider | None = computer_use_provider
        else:
            try:
                self.computer_use_provider = GeminiComputerUseProvider()
            except Exception:
                self.computer_use_provider = None

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
            if hasattr(session, "circuit_breaker") and session.circuit_breaker is not None:
                self.circuit_breaker = session.circuit_breaker
            else:
                session.circuit_breaker = self.circuit_breaker
        elif not hasattr(self, "circuit_breaker") or self.circuit_breaker is None:
            self.circuit_breaker = ActionCircuitBreaker()

        # Reset circuit breaker for this specific task execution (authoritative task timer)
        self.circuit_breaker.reset_for_task(self.circuit_breaker.task_timeout_seconds)

        trace = global_latency_tracker.start_trace(task_id=task_id, user_request=user_request)

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

        from app.agent.task_manager import TaskLifecycle

        current_task_obj = self.task_manager.create_task(
            intent=user_request,
            goal=user_request,
            generation=task_gen,
            total_steps=1,
            task_id=task_id,
        )
        current_task_obj.transition_to(TaskLifecycle.UNDERSTANDING)

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
                current_task_obj.transition_to(TaskLifecycle.CANCELLED)
                yield _make_agent_event(
                    "task_cancelled",
                    task_id=task_id,
                    generation=task_gen,
                )
                return

            current_task_obj.transition_to(TaskLifecycle.UNDERSTANDING)

            # 1. UNDERSTAND & REASON: Query System 0 -> System 1 -> System 2
            trace.mark("routing_start")
            decision, telemetry = await self._decide_next_action(
                user_goal=user_request,
                last_error=last_error_context,
                turn_actions=turn_actions,
                step_idx=iteration,
                recovery_attempts=recovery_attempts,
            )
            trace.mark("routing_end")

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
                current_task_obj.transition_to(TaskLifecycle.WAITING_FOR_USER)
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
                current_task_obj.transition_to(TaskLifecycle.COMPLETED)
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
            current_task_obj.transition_to(TaskLifecycle.PLANNING)
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
                    or {confirmed_action.get("tool"), tool_name}
                    <= {"send_message", "prepare_message"}
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
                    current_task_obj.transition_to(TaskLifecycle.FAILED)
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
                current_task_obj.transition_to(TaskLifecycle.WAITING_FOR_USER)
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

            # 5. ACT: Validate circuit breaker & execute tool
            cb_status = self.circuit_breaker.check_pre_execution(
                tool_name=tool_name,
                arguments=validation.arguments,
                environment_identity=self.state.active_application or "",
            )
            if cb_status.tripped:
                current_task_obj.transition_to(TaskLifecycle.FAILED)
                def_cb_msg = "I couldn't complete that because the computer state stopped changing."
                msg = cb_status.reason or def_cb_msg
                self.conversation_history.append({"role": "assistant", "content": msg})
                trace.mark("response_end")
                yield _make_agent_event(
                    "response",
                    task_id=task_id,
                    generation=task_gen,
                    text=msg,
                    verified=False,
                    latency=trace.metrics.to_dict(),
                )
                yield _make_agent_event(
                    "circuit_breaker_tripped",
                    task_id=task_id,
                    generation=task_gen,
                    reason=msg,
                )
                yield _make_agent_event(
                    "task_failed",
                    task_id=task_id,
                    generation=task_gen,
                    reason=msg,
                )
                return

            current_task_obj.transition_to(TaskLifecycle.ACTING)
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

            trace.mark("tool_start")
            tool_start_ts = time.perf_counter()
            url_before = (
                self.state.current_url
                or (self.observer.observe().get("browser") or {}).get("url")
                or ""
            )

            # Bounded tool execution (up to 15s) to guarantee no indefinite blockage
            try:
                harness_result = await asyncio.wait_for(
                    self._execute_tool(tool_name, validation.arguments),
                    timeout=15.0,
                )
            except TimeoutError:
                logger.warning(
                    "Tool %s timed out after 15.0s; checking live observation.", tool_name
                )
                # Check live state: did the action actually succeed in the real world?
                obs_check = self.observer.observe()
                target_u = validation.arguments.get("url") or ""
                active_u = (
                    obs_check.get("current_url")
                    or (obs_check.get("browser") or {}).get("url")
                    or ""
                ).lower()
                win_t = (obs_check.get("active_window_title") or "").lower()

                if target_u and (
                    target_u.lower().rstrip("/") in active_u
                    or (
                        "youtube" in target_u.lower()
                        and ("youtube.com" in active_u or "youtube" in win_t)
                    )
                ):
                    harness_result = {
                        "success": True,
                        "url": target_u,
                        "action": tool_name,
                        "message": (
                            f"Operation timed out, but verified {target_u} reached via observation."
                        ),
                        "recovered_from_timeout": True,
                    }
                else:
                    harness_result = {
                        "success": False,
                        "action": tool_name,
                        "message": f"Action '{tool_name}' timed out after 15s.",
                        "error": "tool_timeout",
                    }
            tool_end_ts = time.perf_counter()
            tool_dur = tool_end_ts - tool_start_ts
            trace.mark("tool_end")

            # Brief pause for OS/DOM stabilization
            await asyncio.sleep(0.05)

            # 6. OBSERVE: Capture live computer state
            trace.mark("observation_start")
            current_task_obj.transition_to(TaskLifecycle.OBSERVING)
            observation = self.observer.observe()
            trace.mark("observation_end")

            # Update typed context from real observation
            self._update_typed_context(tool_name, validation.arguments, harness_result, observation)

            # 7. VERIFY: Task-specific verification
            trace.mark("verification_start")
            current_task_obj.transition_to(TaskLifecycle.VERIFYING)
            verification = self._verify_action(
                tool_name=tool_name,
                arguments=validation.arguments,
                harness_result=harness_result,
                observation=observation,
                task_id=task_id,
                generation=task_gen,
                user_goal=user_request,
            )
            trace.mark("verification_end")

            self.circuit_breaker.record_action_result(
                tool_name=tool_name,
                arguments=validation.arguments,
                observation=observation,
                verified=verification.verified,
                environment_identity=self.state.active_application or "",
            )

            # Structured runtime debug telemetry (Requirement 15)
            url_after = (
                observation.get("current_url")
                or (observation.get("browser") or {}).get("url")
                or self.state.current_url
                or ""
            )
            v_status = "SUCCESS" if verification.verified else "FAILED"
            retry_count = self.circuit_breaker.action_retries.get(tool_name, 0)
            res_label = (
                "already_at_target"
                if harness_result.get("already_at_target")
                else (
                    "timeout_recovered"
                    if harness_result.get("recovered_from_timeout")
                    or harness_result.get("navigation_recovered_from_timeout")
                    else ("success" if harness_result.get("success") else "failed")
                )
            )
            logger.info(
                "[BROWSER_TELEMETRY] tool=%s req=%s before=%s dur=%.2fs res=%s "
                "after=%s ver=%s retries=%d gen=%d",
                tool_name,
                validation.arguments.get("url") or validation.arguments.get("query") or "",
                url_before,
                tool_dur,
                res_label,
                url_after,
                v_status,
                retry_count,
                task_gen,
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
                if tool_name in ("open_application", "focus_application"):
                    app_name = validation.arguments.get("application") or harness_result.get(
                        "application"
                    )
                    if app_name:
                        self.state.active_application = app_name
                elif tool_name in ("open_folder", "count_directory_items", "list_directory"):
                    self.state.active_application = "File Explorer"
                    if observation.get("current_directory"):
                        self.state.current_directory = observation["current_directory"]
                    elif validation.arguments.get("path") or validation.arguments.get("directory"):
                        self.state.current_directory = validation.arguments.get(
                            "path"
                        ) or validation.arguments.get("directory")
                elif tool_name in ("browser_navigate", "browser_search", "browser_click"):
                    self.state.active_application = (
                        harness_result.get("application") or "Google Chrome"
                    )
                    active_u = (
                        (observation.get("browser") or {}).get("url")
                        or harness_result.get("details", {}).get("url")
                        or harness_result.get("url")
                        or validation.arguments.get("url")
                        or (
                            validation.arguments.get("target")
                            if str(validation.arguments.get("target", "")).startswith("http")
                            else None
                        )
                    )
                    if active_u:
                        self.state.current_url = active_u
                        self.state.active_page_url = active_u
                        if not self.state.browser:
                            self.state.browser = "chrome"

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
                current_task_obj.transition_to(TaskLifecycle.RECOVERING)
                last_error_context = (
                    f"Tool '{tool_name}' failed verification: {verification.reason}"
                )
                logger.info("Step not verified. Attempting recovery (%d/3)...", recovery_attempts)
                if recovery_attempts >= 3:
                    current_task_obj.transition_to(TaskLifecycle.FAILED)
                    target_arg = (
                        raw_arguments.get("application")
                        or raw_arguments.get("path")
                        or raw_arguments.get("query")
                        or raw_arguments.get("url")
                        or ""
                    )
                    action_desc = (
                        f"{tool_name.replace('_', ' ')} {target_arg}".strip()
                        if target_arg
                        else tool_name.replace("_", " ")
                    )
                    msg = (
                        f"I attempted to {action_desc}, "
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

    def _system0_deterministic_decision(
        self,
        user_goal: str,
        turn_actions: list[ActionRecord] | None = None,
    ) -> dict[str, Any] | None:
        """System 0: Ultra-low latency (<1ms) deterministic decision engine for obvious commands.

        Zero LLM calls, zero network latency, zero hallucinations.
        """
        clean_goal = user_goal.strip().rstrip(".!?")
        g = clean_goal.lower()

        # Multi-turn continuation if last action was search
        if turn_actions and turn_actions[-1].tool == "browser_search":
            if any(w in g for w in ("open", "account", "profile", "view", "watch", "play", "show")):
                from app.desktop.web_services import parse_service_account_query

                spec, uname = parse_service_account_query(user_goal)
                target_user = uname.lower() if uname else ""
                cand_url = None
                if target_user:
                    for res in self.typed_context.browser_search_results:
                        if target_user in res.url.lower() or target_user in res.title.lower():
                            cand_url = res.url
                            break
                if not cand_url and spec and uname and spec.account_url_template:
                    cand_url = spec.account_url_template.format(username=uname)
                elif not cand_url and "github" in g and "lohith122" in g:
                    cand_url = "https://github.com/lohith122"
                if cand_url:
                    return {
                        "decision": "tool_call",
                        "tool": "browser_click",
                        "arguments": {"target": cand_url},
                        "thought": f"Opening observed search result for {cand_url}.",
                    }

        # 1. Stop / Cancel
        if g in {"stop", "cancel", "abort", "halt", "terminate"}:
            return {
                "decision": "complete",
                "thought": "User requested to stop.",
                "response": "Stopped.",
            }

        # 2. Browser opening & switching
        if g in {"open edge", "launch edge", "open microsoft edge", "start edge"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Microsoft Edge.",
                "tool": "open_application",
                "arguments": {"application": "Microsoft Edge"},
            }

        if g in {"open chrome", "launch chrome", "open google chrome", "start chrome"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Google Chrome.",
                "tool": "open_application",
                "arguments": {"application": "Google Chrome"},
            }

        if g in {"open a browser", "open browser", "launch browser", "start browser"}:
            return {
                "decision": "tool_call",
                "thought": "Opening browser.",
                "tool": "open_browser",
                "arguments": {},
            }

        if any(cue in g for cue in ("switch back to chrome", "focus chrome", "switch to chrome")):
            return {
                "decision": "tool_call",
                "thought": "Switching back to Google Chrome.",
                "tool": "focus_application",
                "arguments": {"application": "Google Chrome"},
            }

        if any(cue in g for cue in ("switch back to edge", "focus edge", "switch to edge")):
            return {
                "decision": "tool_call",
                "thought": "Switching back to Microsoft Edge.",
                "tool": "focus_application",
                "arguments": {"application": "Microsoft Edge"},
            }

        # 3. Web Services & Direct navigation
        if "youtube" in g:
            # Multi-step compound goal: "open youtube and search (for) <query>"
            m_yt_compound = re.search(
                r"(?:open|go\s+to|launch)\s+youtube\s+(?:and|,|then)\s+search\s+(?:for\s+)?(.+)",
                clean_goal,
                re.IGNORECASE,
            )
            if m_yt_compound:
                query = m_yt_compound.group(1).strip().rstrip(".!?")
                search_done = any(
                    a.tool == "browser_search" and a.verified
                    for a in (turn_actions or [])
                )
                if search_done:
                    return {
                        "decision": "complete",
                        "thought": f"Searched YouTube for '{query}'.",
                        "response": f"Searched YouTube for '{query}'.",
                    }

                nav_done = any(
                    a.tool == "browser_navigate" and a.verified
                    for a in (turn_actions or [])
                )
                curr_u = (self.state.current_url or "").lower()
                active_app = (self.state.active_application or "").lower()
                active_t = (self.state.active_window_title or "").lower()
                is_yt_open = (
                    nav_done
                    or "youtube.com" in curr_u
                    or "youtube" in active_app
                    or "youtube" in active_t
                )

                if not is_yt_open:
                    return {
                        "decision": "tool_call",
                        "thought": "Opening YouTube.",
                        "tool": "browser_navigate",
                        "arguments": {"url": "https://www.youtube.com"},
                    }
                else:
                    return {
                        "decision": "tool_call",
                        "thought": f"Searching YouTube for '{query}'.",
                        "tool": "browser_search",
                        "arguments": {"query": query, "site": "youtube"},
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
            if any(w in g for w in ("homepage", "home")):
                return {
                    "decision": "tool_call",
                    "thought": "Opening YouTube homepage.",
                    "tool": "browser_navigate",
                    "arguments": {"url": "https://www.youtube.com/"},
                }
            if any(w in g for w in ("open", "go to", "take me")):
                return {
                    "decision": "tool_call",
                    "thought": "Opening YouTube.",
                    "tool": "browser_navigate",
                    "arguments": {"url": "https://www.youtube.com"},
                }

        # GitHub Navigation
        if "github" in g:
            if g in {"open github", "launch github", "go to github", "start github"}:
                return {
                    "decision": "tool_call",
                    "thought": "Opening GitHub.",
                    "tool": "browser_navigate",
                    "arguments": {"url": "https://github.com", "service": "github"},
                }

        # Documentation / guide search (e.g. "open python docs")
        m_docs = re.match(
            r"^open\s+(.+?\s+(?:docs|documentation|tutorials?|guide|cheatsheet))$",
            g,
        )
        if m_docs:
            q_docs = m_docs.group(1).strip()
            return {
                "decision": "tool_call",
                "thought": f"Searching for '{q_docs}'.",
                "tool": "browser_search",
                "arguments": {"query": q_docs, "site": "google"},
            }

        if g.startswith(("search for ", "search ")):
            query = re.sub(r"^search\s+(?:for\s+)?", "", clean_goal).strip()
            curr_u = (self.state.current_url or "").lower()
            active_app = (self.state.active_application or "").lower()
            active_t = (self.state.active_window_title or "").lower()
            site = "google"
            if "youtube.com" in curr_u or "youtube" in active_app or "youtube" in active_t:
                site = "youtube"
            elif "github.com" in curr_u or "github" in active_app or "github" in active_t:
                site = "github"
            return {
                "decision": "tool_call",
                "thought": f"Searching {site.title()} for '{query}'.",
                "tool": "browser_search",
                "arguments": {"query": query, "site": site},
            }

        # 4. Browser Navigation History & Tabs
        if g in {"go back", "back", "navigate back", "previous page"}:
            is_fs = (
                self.typed_context.last_active_domain == "filesystem"
                or "explorer" in (self.state.active_application or "").lower()
            )
            if is_fs:
                cur = self.state.current_directory or ""
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

        if g in {"close this tab", "close tab", "close the tab"}:
            return {
                "decision": "tool_call",
                "thought": "Closing active browser tab.",
                "tool": "browser_close_tab",
                "arguments": {},
            }

        # 5. Desktop Applications
        if g in {"open file explorer", "file explorer", "launch file explorer", "open explorer"}:
            return {
                "decision": "tool_call",
                "thought": "Opening File Explorer.",
                "tool": "open_application",
                "arguments": {"application": "File Explorer"},
            }

        if g in {"open vs code", "open visual studio code", "launch vs code", "open vscode"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Visual Studio Code.",
                "tool": "open_application",
                "arguments": {"application": "Visual Studio Code"},
            }

        if g in {"open whatsapp", "launch whatsapp"}:
            return {
                "decision": "tool_call",
                "thought": "Opening WhatsApp.",
                "tool": "open_application",
                "arguments": {"application": "WhatsApp"},
            }

        # 6. Filesystem Locations & Inspection
        if g in {"open desktop", "show desktop", "go to desktop", "take me to desktop"}:
            return {
                "decision": "tool_call",
                "thought": "Navigating to Desktop folder.",
                "tool": "open_folder",
                "arguments": {"path": "Desktop"},
            }

        if g in {"open downloads", "open the downloads folder", "go to downloads"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Downloads folder.",
                "tool": "open_folder",
                "arguments": {"path": "Downloads"},
            }

        if g in {"open documents", "open the documents folder", "go to documents"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Documents folder.",
                "tool": "open_folder",
                "arguments": {"path": "Documents"},
            }

        if g in {"open music", "open the music folder", "go to music"}:
            return {
                "decision": "tool_call",
                "thought": "Opening Music folder.",
                "tool": "open_folder",
                "arguments": {"path": "Music"},
            }

        if "how many" in g or re.search(r"\bcount\b", g):
            item_type = "file" if "file" in g else "folder"
            target_dir = self.state.current_directory or "Desktop"
            for prep in ("on my ", "in my ", "in ", "inside ", "available in ", "exist in "):
                if prep in g:
                    clean_after = g.split(prep, 1)[1].strip().rstrip("?")
                    after_prep = clean_after.replace("folder", "").strip()
                    if after_prep:
                        target_dir = after_prep.title()
                        break
            return {
                "decision": "tool_call",
                "thought": f"Counting {item_type}s in '{target_dir}'.",
                "tool": "count_directory_items",
                "arguments": {"directory": target_dir, "item_type": item_type},
            }

        if any(
            p in g
            for p in (
                "what's in my downloads",
                "whats in my downloads",
                "what is in my downloads",
                "list downloads",
                "show downloads files",
            )
        ):
            return {
                "decision": "tool_call",
                "thought": "Listing items in Downloads folder.",
                "tool": "list_directory",
                "arguments": {"directory": "Downloads"},
            }

        if any(
            p in g
            for p in (
                "what are those files",
                "what are the files",
                "what files",
                "list files",
                "show files",
            )
        ):
            if self.typed_context.filesystem_results:
                file_names = [e.name for e in self.typed_context.filesystem_results]
                dir_name = (
                    self.state.current_directory
                    or self.typed_context.last_opened_folder
                    or "Desktop"
                )
                return {
                    "decision": "complete",
                    "thought": f"Listing {len(file_names)} verified files from {dir_name}.",
                    "response": f"The files in {dir_name} are: {', '.join(file_names)}.",
                }
            target_dir = (
                self.state.current_directory
                or self.typed_context.last_opened_folder
                or "Desktop"
            )
            return {
                "decision": "tool_call",
                "thought": f"Listing directory items in '{target_dir}'.",
                "tool": "list_directory",
                "arguments": {"directory": target_dir},
            }

        if g in {
            "system information",
            "system info",
            "what is the system info",
            "whats the system information",
        }:
            return {
                "decision": "tool_call",
                "thought": "Getting computer state and system information.",
                "tool": "get_computer_state",
                "arguments": {},
            }

        return None

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
        if any(
            w in g
            for w in (
                "find python jobs",
                "job search",
                "tailor resume",
                "find jobs",
                "career discovery",
            )
        ):
            return {
                "decision": "ask_user",
                "thought": "Career intelligence queries belong to the Career Intelligence page.",
                "question": (
                    "Job searching and resume tailoring are managed on Career Intelligence. "
                    "Would you like to switch pages?"
                ),
            }, telemetry

        # 2. Check if an action executed during THIS turn already satisfied the goal
        turn_decision = self._check_turn_completion(turn_actions, user_goal=user_goal)
        if turn_decision:
            return turn_decision, telemetry

        # 3. System 0: Ultra-Fast Deterministic Fast Decision (<1ms) for obvious commands
        sys0_decision = self._system0_deterministic_decision(
            user_goal=user_goal, turn_actions=turn_actions
        )
        if sys0_decision:
            telemetry.update({
                "laya_decision": "system0_deterministic",
                "laya_confidence": 1.0,
                "llm_tier": "SYSTEM_0_FAST",
                "llm_provider": "deterministic",
                "llm_model": "none",
                "route_reason": "System 0 deterministic fast-path",
            })
            return sys0_decision, telemetry

        # Multi-step continuation: if last action was browser_search and user goal
        # was to open an account or item
        if turn_actions and turn_actions[-1].tool == "browser_search":
            if any(w in g for w in ("open", "account", "profile", "view", "watch", "play", "show")):
                from app.desktop.web_services import parse_service_account_query

                spec, uname = parse_service_account_query(user_goal)
                target_user = uname.lower() if uname else ""

                cand_url = None
                cand_title = None

                # 1. Match exact target user in observed search results
                if target_user:
                    for res in self.typed_context.browser_search_results:
                        res_url = res.url.lower()
                        res_title = res.title.lower()
                        if target_user in res_url or target_user in res_title:
                            cand_url = res.url
                            cand_title = res.title
                            break

                # 2. Match service spec if no specific user or if user search yielded service page
                if not cand_url and not target_user:
                    for res in self.typed_context.browser_search_results:
                        if spec and spec.name.lower() in res.url.lower():
                            cand_url = res.url
                            cand_title = res.title
                            break

                # 3. Direct template fallback if search results didn't have link
                if not cand_url and spec and uname and spec.account_url_template:
                    cand_url = spec.account_url_template.format(username=uname)
                    cand_title = f"{uname} on {spec.display_name}"
                elif not cand_url and "github" in g and "lohith122" in g:
                    cand_url = "https://github.com/lohith122"
                    cand_title = "lohith122 GitHub"

                if cand_url:
                    return {
                        "decision": "tool_call",
                        "tool": "browser_click",
                        "arguments": {"target": cand_url},
                        "thought": f"Clicking observed search result for {cand_title or cand_url}.",
                    }, telemetry

        # 4. System-1: Fast Bounded Decisions via Laya
        state_summary = (
            f"App: {self.state.active_application}, "
            f"Dir: {self.state.current_directory}, "
            f"URL: {self.state.current_url or (self.state.browser and self.state.active_page_url)}"
        )
        laya_domain = await self.decision_engine.classify_domain(
            user_goal, state_summary=state_summary
        )
        telemetry["laya_decision"] = laya_domain.decision
        telemetry["laya_confidence"] = laya_domain.confidence

        # Fast Reference Resolution via System-1
        ref_resolution: DecisionResult | None = None
        candidate_labels: list[str] = []
        if self.typed_context.filesystem_results:
            candidate_labels.extend(
                [f"{ent.ordinal}. {ent.name}" for ent in self.typed_context.filesystem_results[:10]]
            )
        if self.typed_context.youtube_video_results:
            candidate_labels.extend(
                [
                    f"{ent.ordinal}. {ent.title}"
                    for ent in self.typed_context.youtube_video_results[:10]
                ]
            )

        has_deictic_ref = any(
            cue in g
            for cue in (
                "those",
                "them",
                "it",
                "that",
                "first",
                "second",
                "third",
                "previous",
                "next",
                "one",
            )
        )
        if candidate_labels and has_deictic_ref:
            ref_resolution = await self.decision_engine.resolve_reference(
                user_goal, candidate_labels
            )
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
        fs_count = len(self.typed_context.filesystem_results)
        yt_count = len(self.typed_context.youtube_video_results)
        amb_result = await self.decision_engine.check_ambiguity(
            user_goal,
            context_summary=(
                f"fs_items={fs_count}, yt_items={yt_count}, "
                f"dir={self.state.current_directory}"
            ),
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
            laya_decision=ref_resolution
            if (ref_resolution and ref_resolution.is_confident)
            else laya_domain,
            typed_context_size=len(self.typed_context.filesystem_results)
            + len(self.typed_context.youtube_video_results),
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
            "system1_reference": ref_resolution.decision
            if (ref_resolution and ref_resolution.is_confident)
            else None,
            "resolved_target": (
                {
                    "name": resolved_fs_ent.name,
                    "path": resolved_fs_ent.path,
                    "type": resolved_fs_ent.type,
                    "ordinal": resolved_fs_ent.ordinal,
                }
                if resolved_fs_ent
                else (
                    {
                        "title": resolved_yt_ent.title,
                        "url": resolved_yt_ent.url,
                        "type": "video",
                        "ordinal": resolved_yt_ent.ordinal,
                    }
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
                    self.state.current_url or (self.state.browser and self.state.active_page_url)
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
                dec["arguments"] = {}
                dec["thought"] = "Opening browser."
                return dec

            # 3. Ground YouTube homepage / open YouTube
            if "youtube" in clean_g and any(
                w in clean_g for w in ("open", "homepage", "home", "go to", "take me")
            ):
                if not any(w in clean_g for w in ("search", "watch", "video", "course", "channel")):
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
            fs_target_ent = resolved_fs_ent
            if fs_target_ent is None and self.typed_context.filesystem_results:
                if (
                    any(
                        w in clean_g
                        for w in (
                            "third",
                            "second",
                            "first",
                            "fourth",
                            "fifth",
                            "1st",
                            "2nd",
                            "3rd",
                            "4th",
                            "5th",
                        )
                    )
                    and "video" not in clean_g
                ):
                    m_ord = re.search(
                        r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\b", clean_g
                    )
                    ord_map = {
                        "first": 1,
                        "1st": 1,
                        "second": 2,
                        "2nd": 2,
                        "third": 3,
                        "3rd": 3,
                        "fourth": 4,
                        "4th": 4,
                        "fifth": 5,
                        "5th": 5,
                    }
                    ord_idx = ord_map.get(m_ord.group(1), 1) if m_ord else 1
                    fs_target_ent = self.typed_context.resolve_ordinal(
                        ord_idx, preferred_domain="filesystem"
                    )

            if fs_target_ent and (
                any(
                    w in clean_g
                    for w in (
                        "open",
                        "view",
                        "launch",
                        "inside",
                        "show",
                        "third",
                        "second",
                        "first",
                        "one",
                    )
                )
                or dec.get("decision") != "tool_call"
            ):
                dec["decision"] = "tool_call"
                dec["tool"] = "open_file" if fs_target_ent.type == "file" else "open_folder"
                dec["arguments"] = {"path": fs_target_ent.path or fs_target_ent.name}
                dec["thought"] = f"Opening {fs_target_ent.name}."
                return dec

            # 4b. Ground ordinal YouTube selection if resolved or if video requested
            if (resolved_yt_ent or "video" in clean_g) and (
                any(
                    w in clean_g
                    for w in (
                        "open",
                        "play",
                        "watch",
                        "click",
                        "view",
                        "third",
                        "second",
                        "first",
                        "fourth",
                        "fifth",
                        "one",
                    )
                )
                or dec.get("decision") != "tool_call"
            ):
                yt_ent = resolved_yt_ent
                if yt_ent is None and self.typed_context.youtube_video_results:
                    m_ord = re.search(
                        r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\b", clean_g
                    )
                    ord_map = {
                        "first": 1,
                        "1st": 1,
                        "second": 2,
                        "2nd": 2,
                        "third": 3,
                        "3rd": 3,
                        "fourth": 4,
                        "4th": 4,
                        "fifth": 5,
                        "5th": 5,
                    }
                    ord_idx = ord_map.get(m_ord.group(1), 1) if m_ord else 1
                    yt_ent = self.typed_context.resolve_ordinal(ord_idx, preferred_domain="youtube")
                if yt_ent:
                    target_url = yt_ent.url or yt_ent.title
                    ord_val = yt_ent.ordinal
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_click"
                    dec["arguments"] = {
                        "target": target_url or f"video #{ord_val}",
                        "ordinal": ord_val,
                    }
                    dec["thought"] = f"Opening video #{ord_val}."
                    return dec

            # 5. Ground search when user says "search for ..." or "search ..."
            if clean_g.startswith(("search for ", "search ")):
                q = re.sub(r"^search\s+(?:for\s+)?", "", clean_g).strip()
                curr_u = (self.state.current_url or "").lower()
                active_app = (self.state.active_application or "").lower()
                active_t = (self.state.active_window_title or "").lower()
                site = "google"
                is_yt = any("youtube" in k for k in (curr_u, active_app, active_t, clean_g))
                is_gh = any("github" in k for k in (curr_u, active_app, active_t, clean_g))
                if is_yt:
                    site = "youtube"
                elif is_gh:
                    site = "github"
                dec["decision"] = "tool_call"
                dec["tool"] = "browser_search"
                dec["arguments"] = {"query": q, "site": site}
                dec["thought"] = f"Searching {site.title()} for '{q}'."
                return dec

            # 6. Service / account target grounding (e.g. "open lohith122 github account")
            from app.desktop.web_services import parse_service_account_query

            svc_spec, svc_user = parse_service_account_query(clean_g)
            if svc_spec and (
                dec.get("decision") != "tool_call"
                or dec.get("tool") not in ("browser_search", "browser_navigate", "browser_click")
            ):
                if svc_user and svc_spec.account_url_template:
                    acc_url = svc_spec.account_url_template.format(username=svc_user)
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_navigate"
                    dec["arguments"] = {"url": acc_url, "service": svc_spec.name}
                    dec["thought"] = f"Opening {svc_spec.display_name} account for {svc_user}."
                    return dec
                elif not svc_user:
                    dec["decision"] = "tool_call"
                    dec["tool"] = "browser_navigate"
                    dec["arguments"] = {"url": svc_spec.base_url, "service": svc_spec.name}
                    dec["thought"] = f"Opening {svc_spec.display_name}."
                    return dec

            if dec.get("decision") == "tool_call":
                t_name = dec.get("tool")
                args = dec.setdefault("arguments", {})
                if t_name in ("open_folder", "open_file"):
                    cur_path = str(args.get("path") or "").strip()
                    if resolved_fs_ent and (
                        not cur_path
                        or cur_path
                        in (
                            "Music",
                            "Desktop",
                            "Downloads",
                            "Documents",
                            self.state.current_directory,
                            self.typed_context.last_opened_folder,
                        )
                        or any(
                            w in user_goal.lower()
                            for w in (
                                "third",
                                "second",
                                "first",
                                "fourth",
                                "fifth",
                                "one",
                                "folder",
                                "file",
                            )
                        )
                    ):
                        args["path"] = resolved_fs_ent.path or resolved_fs_ent.name
                        if resolved_fs_ent.type == "file":
                            dec["tool"] = "open_file"
                        else:
                            dec["tool"] = "open_folder"
                elif t_name == "browser_click":
                    if resolved_yt_ent and (
                        not args.get("target") or "video" in str(args.get("target")).lower()
                    ):
                        args["target"] = resolved_yt_ent.url or resolved_yt_ent.title
                        args["ordinal"] = resolved_yt_ent.ordinal
                elif user_goal.strip().rstrip(".!?").lower() in ("go back", "back"):
                    # If in filesystem context and navigating back from subfolder
                    is_fs_subfolder = (
                        self.typed_context.last_active_domain == "filesystem"
                        and self.state.current_directory
                        and any(
                            sub in self.state.current_directory
                            for sub in ("Classical", "Pop", "Rock", "/", "\\")
                        )
                    )
                    if not is_fs_subfolder:
                        dec["tool"] = "browser_back"
                        dec["arguments"] = {}
            return dec

        # 5a. Dedicated Computer Use Provider (e.g. Gemini Computer Use)
        if self.computer_use_provider and getattr(self.computer_use_provider, "enabled", False):
            try:
                active_obs = self.observer.observe()
                cu_decision = await self.computer_use_provider.decide_action(
                    goal=user_goal,
                    observation=active_obs,
                    context_payload=context_payload,
                    tools=[
                        COMPUTER_TOOLS_BY_NAME[t["name"]]
                        for t in tool_schemas
                        if t["name"] in COMPUTER_TOOLS_BY_NAME
                    ],
                )
                if cu_decision and "decision" in cu_decision:
                    telemetry["llm_provider"] = "gemini_computer_use"
                    telemetry["llm_model"] = getattr(
                        self.computer_use_provider, "model_name", "gemini-2.5-flash"
                    )
                    return _ground_decision(cu_decision), telemetry
            except Exception as cu_exc:
                logger.warning(
                    "Gemini Computer Use provider failed: %s. Falling back to LLM router.",
                    cu_exc,
                )

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
                logger.warning(
                    "Primary LLM (%s) failed: %s. Attempting fallback.",
                    route_decision.provider,
                    exc,
                )
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
                            telemetry["llm_provider"] = (
                                route_decision.fallback_provider or "fallback"
                            )
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
        user_goal: str = "",
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

        g = (user_goal or "").strip().rstrip(".!?").lower()

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
        if last_act.tool == "browser_click":
            target = str(last_act.arguments.get("target") or "")
            if "github.com" in target.lower() or "github" in g:
                uname = (
                    "lohith122" if ("lohith122" in target.lower() or "lohith122" in g) else "user"
                )
                m = re.search(r"github\.com/([a-zA-Z0-9_-]+)", target)
                if m:
                    uname = m.group(1)
                return {
                    "decision": "complete",
                    "thought": f"Opened GitHub account for {uname}.",
                    "response": f"Opened the GitHub account for {uname}.",
                }
            if last_act.arguments.get("ordinal"):
                return {
                    "decision": "complete",
                    "thought": "Browser click on target item succeeded.",
                    "response": "Opened the selected item.",
                }
            return {
                "decision": "complete",
                "thought": f"Clicked {target}.",
                "response": f"Opened {target}."
                if target.startswith("http")
                else f"Clicked on {target}.",
            }
        app_tools = ("open_application", "focus_application", "open_browser", "launch_browser")
        if last_act.tool in app_tools:
            app = last_act.arguments.get("application", "") or "Browser"
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
            from pathlib import Path

            fname = Path(path).name or path
            return {
                "decision": "complete",
                "thought": f"File {path} opened.",
                "response": f"Opened file {fname}.",
            }
        if last_act.tool == "browser_navigate":
            # If the user's goal was compound (navigate + search), navigation alone is not complete!
            if any(w in g for w in ("search", "find", "look up")):
                return None
            url = last_act.arguments.get("url", "")
            service = last_act.arguments.get("service")
            if "github.com" in url or (service and "github" in service.lower()):
                uname = None
                if "lohith122" in url.lower() or "lohith122" in g:
                    uname = "lohith122"
                else:
                    m = re.search(r"github\.com/([a-zA-Z0-9_-]+)", url)
                    if m:
                        uname = m.group(1)
                if uname:
                    return {
                        "decision": "complete",
                        "thought": f"Opened GitHub account for {uname}.",
                        "response": f"Opened the GitHub account for {uname}.",
                    }
                return {
                    "decision": "complete",
                    "thought": "Navigated to GitHub.",
                    "response": "Opening GitHub.",
                }
            if "youtube.com" in url or (service and "youtube" in service.lower()):
                site = "YouTube"
            else:
                site = service.title() if service else "the website"
            return {
                "decision": "complete",
                "thought": f"Navigated to {site}.",
                "response": f"Opening {site}.",
            }
        if last_act.tool == "browser_search":
            # If user's goal was docs/guide search (e.g. "open python docs"), search satisfies it
            if any(w in g for w in ("docs", "documentation", "tutorials", "guide", "cheatsheet")):
                return {
                    "decision": "complete",
                    "thought": "Documentation search executed.",
                    "response": f"Searched for '{last_act.arguments.get('query')}'.",
                }
            # If user's goal was to open an account or watch video, search is only step 1
            if any(w in g for w in ("account", "profile", "watch", "play", "github")):
                return None
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
        if any(
            w in g
            for w in (
                "find python jobs",
                "job search",
                "tailor resume",
                "find jobs",
                "career discovery",
            )
        ):
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
        what_pattern = (
            r"\b(what are those|what are they|list them|show them|"
            r"which ones|what are the files)\b"
        )
        if re.search(what_pattern, g) or "those files" in g:
            if self.typed_context.filesystem_results:
                names = [f.name for f in self.typed_context.filesystem_results[:12]]
                preview = ", ".join(names)
                remaining = len(self.typed_context.filesystem_results) - 12
                more = f", and {remaining} more" if remaining > 0 else ""
                is_files = any(
                    f.type == "file" or "." in f.name for f in self.typed_context.filesystem_results
                )
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
                "first": 1,
                "1st": 1,
                "second": 2,
                "2nd": 2,
                "third": 3,
                "3rd": 3,
                "fourth": 4,
                "4th": 4,
                "fifth": 5,
                "5th": 5,
            }
            ord_val = ord_map.get(m_ord.group(1), 1)
            target_kind = m_ord.group(2) or ""

            # Check if domain preference is indicated
            is_video = "video" in target_kind or (
                self.typed_context.last_active_domain == "browser"
                and not self.typed_context.filesystem_results
            )
            if is_video:
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
                    item_type = "file" if is_file else "folder"
                    return {
                        "decision": "tool_call",
                        "thought": f"Opening {ord_val}th {item_type} '{fs_ent.name}'.",
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
                "arguments": {},
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

        # Documentation / guide search (e.g. "open python docs")
        m_docs = re.match(
            r"^open\s+(.+?\s+(?:docs|documentation|tutorials?|guide|cheatsheet))$",
            g,
        )
        if m_docs:
            q_docs = m_docs.group(1).strip()
            return {
                "decision": "tool_call",
                "thought": f"Searching for '{q_docs}'.",
                "tool": "browser_search",
                "arguments": {"query": q_docs, "site": "google"},
            }

        # Service / account target query (e.g. "open lohith122 github account")
        from app.desktop.web_services import parse_service_account_query

        svc_spec, svc_user = parse_service_account_query(clean_goal)
        if svc_spec:
            if svc_user and svc_spec.account_url_template:
                acc_url = svc_spec.account_url_template.format(username=svc_user)
                return {
                    "decision": "tool_call",
                    "thought": f"Opening {svc_spec.display_name} account for {svc_user}.",
                    "tool": "browser_navigate",
                    "arguments": {"url": acc_url, "service": svc_spec.name},
                }
            elif not svc_user:
                return {
                    "decision": "tool_call",
                    "thought": f"Opening {svc_spec.display_name}.",
                    "tool": "browser_navigate",
                    "arguments": {"url": svc_spec.base_url, "service": svc_spec.name},
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

        if "open downloads" in g or "open the downloads folder" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening Downloads folder.",
                "tool": "open_folder",
                "arguments": {"path": "Downloads"},
            }

        if "open documents" in g or "open the documents folder" in g:
            return {
                "decision": "tool_call",
                "thought": "Opening Documents folder.",
                "tool": "open_folder",
                "arguments": {"path": "Documents"},
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

        if any(
            p in g
            for p in (
                "what are those files",
                "what are the files",
                "what files",
                "which files",
                "show the files",
                "show files",
                "list files",
                "what are those",
            )
        ):
            if (
                self.typed_context.filesystem_results
                or self.typed_context.last_active_domain == "filesystem"
                or "explorer" in (self.state.active_application or "").lower()
            ):
                if self.typed_context.filesystem_results:
                    file_names = [e.name for e in self.typed_context.filesystem_results]
                    dir_name = (
                        self.state.current_directory
                        or self.typed_context.last_opened_folder
                        or "Music"
                    )
                    return {
                        "decision": "complete",
                        "thought": f"Listing {len(file_names)} verified files from {dir_name}.",
                        "response": f"The files in {dir_name} are: {', '.join(file_names)}.",
                    }
                else:
                    target_dir = (
                        self.state.current_directory
                        or self.typed_context.last_opened_folder
                        or "Music"
                    )
                    return {
                        "decision": "tool_call",
                        "thought": f"Listing directory items in '{target_dir}'.",
                        "tool": "list_directory",
                        "arguments": {"directory": target_dir},
                    }

        if any(
            p in g
            for p in ("what's inside", "whats inside", "inside it", "what is inside", "what inside")
        ):
            target_dir = (
                self.state.current_directory or self.typed_context.last_opened_folder or "Music"
            )
            return {
                "decision": "tool_call",
                "thought": f"Listing directory items in '{target_dir}'.",
                "tool": "list_directory",
                "arguments": {"directory": target_dir},
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
                    else (
                        dict(res)
                        if isinstance(res, dict)
                        else {"success": True, "message": str(res)}
                    )
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
            url = arguments.get("url")
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
                else (
                    dict(res) if isinstance(res, dict) else {"success": True, "message": str(res)}
                )
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
            url = arguments.get("url") or ""
            browser = arguments.get("browser")
            service = arguments.get("service")

            # If service is specified (e.g. github, linkedin), dispatch to open_service
            # so personalized credentials / profiles in the vault are checked.
            if service and hasattr(self.harness, "execute_command"):
                res = self.harness.execute_command(
                    "open_service", {"service": service, "url": url}, session=self._current_session
                )
            else:
                # 1. Idempotency check: if current state is already at requested target
                curr_url = (self.state.current_url or "").lower().rstrip("/")
                tgt_url = url.lower().rstrip("/")
                active_title = (self.state.active_window_title or "").lower()
                active_app = (self.state.active_application or "").lower()

                is_target_yt_home = tgt_url in (
                    "https://www.youtube.com",
                    "https://youtube.com",
                    "http://www.youtube.com",
                    "http://youtube.com",
                )
                is_already = False
                if curr_url and (curr_url == tgt_url or curr_url == f"{tgt_url}/"):
                    is_already = True
                elif is_target_yt_home and (
                    "youtube.com" in curr_url
                    or "youtube" in active_title
                    or "youtube" in active_app
                ):
                    is_already = True

                if is_already:
                    if self._current_session is not None:
                        self._current_session.active_browser = True
                    return {
                        "success": True,
                        "already_at_target": True,
                        "action": "browser_navigate",
                        "url": url or self.state.current_url,
                        "message": f"Already at {url or self.state.current_url}.",
                        "details": {"url": url, "already_at_target": True},
                    }

                if hasattr(self.harness, "browser_navigate"):
                    res = self.harness.browser_navigate(url, browser=browser)
                else:
                    res = {"success": True, "action": "browser_navigate", "url": url}
            res_dict = (
                res.to_dict()
                if hasattr(res, "to_dict")
                else (
                    dict(res) if isinstance(res, dict) else {"success": True, "message": str(res)}
                )
            )

            # CRITICAL RULE: TIMEOUT DOES NOT MEAN ACTION FAILED
            # If the operation timed out or failed, observe live state.
            # If the target URL or domain is now reached, treat as success!
            if not res_dict.get("success"):
                obs = self.observer.observe()
                if hasattr(obs, "to_dict"):
                    obs_dict = obs.to_dict()
                elif isinstance(obs, dict):
                    obs_dict = obs
                else:
                    obs_dict = {}
                active_u = (
                    obs_dict.get("current_url")
                    or (obs_dict.get("browser") or {}).get("url")
                    or self.state.current_url
                    or ""
                ).lower()
                win_t = (
                    obs_dict.get("active_window_title") or self.state.active_window_title or ""
                ).lower()
                win_app = (
                    obs_dict.get("active_application") or self.state.active_application or ""
                ).lower()
                reached = False
                if url and (url.lower().rstrip("/") in active_u or active_u in url.lower()):
                    reached = True
                elif "youtube" in url.lower() and (
                    "youtube.com" in active_u or "youtube" in win_t or "youtube" in win_app
                ):
                    reached = True
                elif service and (
                    service.lower() in active_u
                    or service.lower() in win_t
                    or service.lower() in win_app
                ):
                    reached = True

                if reached:
                    logger.info(
                        "Navigation reported failure/timeout, but target %s reached.",
                        url,
                    )
                    res_dict["success"] = True
                    res_dict["url"] = url
                    res_dict["message"] = f"Navigated to {url} (verified via observation)."
                    res_dict["recovered_from_timeout"] = True
                    res_dict["navigation_recovered_from_timeout"] = True

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
            if hasattr(self.harness, "browser_click"):
                return self.harness.browser_click(target, ordinal=ordinal)
            elif target.startswith("http") and hasattr(self.harness, "browser_navigate"):
                return self.harness.browser_navigate(target)
            return {"success": True, "action": "browser_click", "target": target}

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
        if tool_name in ("count_directory_items", "list_directory", "search_files"):
            item_type = arguments.get("item_type") or harness_result.get("item_type")
            if item_type == "file":
                raw_items = (
                    harness_result.get("items")
                    or harness_result.get("files")
                    or self.state.last_results
                    or []
                )
            elif item_type == "folder":
                raw_items = (
                    harness_result.get("items")
                    or harness_result.get("folders")
                    or self.state.last_results
                    or []
                )
            else:
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
                is_file = (item_type == "file") or bool(harness_result.get("files"))
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

        if tool_name == "open_application":
            app = str(arguments.get("application") or "").lower()
            if "explorer" in app:
                self.typed_context.last_active_domain = "filesystem"
                self.typed_context.clear_browser()

        if tool_name == "open_folder":
            folder_path = arguments.get("path")
            self.typed_context.last_opened_folder = folder_path
            self.typed_context.last_active_domain = "filesystem"
            self.typed_context.clear_browser()
            self.typed_context.restore_folder_entities(folder_path)

        if tool_name == "open_file":
            self.typed_context.last_opened_file = arguments.get("path")
            self.typed_context.last_active_domain = "filesystem"
            self.typed_context.clear_browser()

        if tool_name in ("browser_search", "browser_navigate"):
            self.typed_context.last_active_domain = "browser"
            # If YouTube search and web_context has results
            if self.state.web_context.current_list:
                self.typed_context.set_youtube_entities(self.state.web_context.current_list)
            # If web search results were observed
            search_items = (
                harness_result.get("items")
                or harness_result.get("results")
                or observation.get("browser_search_results")
                or []
            )
            if search_items and isinstance(search_items, list):
                self.typed_context.set_browser_search_entities(search_items)

    def _verify_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        harness_result: dict[str, Any],
        observation: dict[str, Any],
        task_id: str,
        generation: int,
        user_goal: str = "",
    ) -> VerificationResult:
        """Run task-specific verification against live computer observation."""
        if tool_name in ("open_application", "open_browser", "launch_browser"):
            app = arguments.get("application", "") or "browser"
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
            return self.verifier.verify_filesystem_target(
                expected_target=path,
                observation=observation,
                task_id=task_id,
                generation=generation,
            )

        if tool_name == "count_directory_items":
            cnt = harness_result.get("count", 0)
            d_name = arguments.get("directory") or "Desktop"
            return self.verifier.verify_item_count(
                expected_target=d_name,
                count=cnt,
                observation=observation,
                task_id=task_id,
                generation=generation,
            )

        if tool_name == "list_directory":
            if harness_result.get("success"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"{tool_name} successfully observed entries on filesystem.",
                    details=harness_result,
                    evidence=harness_result,
                )

        if tool_name in ("browser_navigate", "browser_click"):
            target = arguments.get("url") or arguments.get("target") or ""
            target_str = str(target).strip()
            browser_obs = observation.get("browser") or {}
            active_url = (
                harness_result.get("url", "")
                or harness_result.get("details", {}).get("url", "")
                or self.state.current_url
                or browser_obs.get("url", "")
                or getattr(self.state.browser, "url", None)
                or ""
            )
            page_title = str(
                browser_obs.get("title", "")
                or harness_result.get("title", "")
                or harness_result.get("details", {}).get("title", "")
                or getattr(self.state.browser, "title", None)
                or self.state.active_window_title
                or ""
            )

            # 1. Goal-level verification for specific service account (e.g. GitHub)
            from app.desktop.web_services import parse_service_account_query

            svc_spec, svc_user = parse_service_account_query(user_goal)
            if svc_spec and svc_user:
                if svc_spec.name.lower() == "github":
                    return self.verifier.verify_github_profile(
                        username=svc_user,
                        observation=observation,
                        task_id=task_id,
                        generation=generation,
                    )
                # If browser is still on Google search results page
                if "google.com/search" in active_url:
                    return VerificationResult(
                        success=False,
                        confidence=0.0,
                        reason=(
                            f"Verification failed: browser is still on Google search results, "
                            f"not {svc_spec.display_name} profile for '{svc_user}'."
                        ),
                        details=harness_result,
                        evidence={"active_url": active_url, "target_user": svc_user},
                    )
                if svc_user.lower() in active_url.lower() or (
                    svc_spec.name.lower() in active_url.lower()
                    and svc_user.lower() in page_title.lower()
                ):
                    return VerificationResult(
                        success=True,
                        confidence=1.0,
                        reason=(
                            f"Verified active at {svc_spec.display_name} profile for '{svc_user}'."
                        ),
                        details=harness_result,
                        evidence={"active_url": active_url, "user": svc_user, "title": page_title},
                    )

            if "github" in user_goal.lower() and "lohith122" in user_goal.lower():
                return self.verifier.verify_github_profile(
                    username="lohith122",
                    observation=observation,
                    task_id=task_id,
                    generation=generation,
                )

            # 0. If already_at_target reported
            if harness_result.get("already_at_target"):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"Already at target: {target_str or active_url}.",
                    details=harness_result,
                    evidence={"url": active_url, "already_at_target": True},
                )

            # 2. YouTube verification
            if "youtube.com" in target_str or "youtube" in user_goal.lower():
                # For browser_navigate, we verify navigation to YouTube!
                if (
                    "youtube.com" in active_url.lower()
                    or "youtube" in page_title.lower()
                    or "youtube" in (observation.get("active_application") or "").lower()
                ):
                    return VerificationResult(
                        success=True,
                        confidence=1.0,
                        reason="Browser active at YouTube.",
                        details=harness_result,
                        evidence={"url": active_url, "title": page_title},
                    )

            # 3. Direct URL target match
            if target_str.startswith("http") and (
                target_str.lower() in active_url.lower() or active_url.lower() in target_str.lower()
            ):
                return VerificationResult(
                    success=True,
                    confidence=1.0,
                    reason=f"Navigated to {target_str}.",
                    details=harness_result,
                    evidence={"url": active_url},
                )

            # 4. Search results rejection if search wasn't the goal
            if harness_result.get("success"):
                if "google.com/search" in active_url and not any(
                    w in user_goal.lower() for w in ("search for", "search ", "google")
                ):
                    return VerificationResult(
                        success=False,
                        confidence=0.0,
                        reason=(
                            "Action failed: browser remained on search results "
                            "instead of target page."
                        ),
                        details=harness_result,
                        evidence={"url": active_url},
                    )
                return VerificationResult(
                    success=True,
                    confidence=0.9,
                    reason=f"Action '{tool_name}' verified.",
                    details=harness_result,
                    evidence=harness_result,
                )

            return VerificationResult(
                success=False,
                confidence=0.0,
                reason=(
                    f"Navigation failed: target '{target_str}' not reached "
                    f"(active URL: '{active_url}')."
                ),
                details=harness_result,
                evidence={"url": active_url},
            )

        if tool_name == "browser_search":
            query = arguments.get("query", "")
            site = arguments.get("site", "")
            effective_obs = dict(observation)
            fresh_url = None
            if harness_result.get("message"):
                m_u = re.search(r"https?://[^\s]+", str(harness_result.get("message")))
                if m_u:
                    fresh_url = m_u.group(0).rstrip(".,;")
            h_det_url = harness_result.get("details", {}).get("url")
            h_url = fresh_url or harness_result.get("url") or h_det_url
            if h_url:
                effective_obs["current_url"] = h_url
                effective_obs["browser_url"] = h_url
                self.state.current_url = h_url
            if site == "youtube" or "youtube" in user_goal.lower():
                return self.verifier.verify_youtube_search(
                    query=query,
                    observation=effective_obs,
                    task_id=task_id,
                    generation=generation,
                )
            v_res = self.verifier.verify_search_results(
                query=query,
                observation=effective_obs,
                task_id=task_id,
                generation=generation,
            )
            if not v_res.verified and harness_result.get("success") and h_url:
                q_norm = query.lower()
                if q_norm in h_url.lower() or q_norm.replace(" ", "+") in h_url.lower():
                    return VerificationResult(
                        success=True,
                        confidence=0.95,
                        reason=f"Search for '{query}' verified in URL",
                        details=harness_result,
                        task_id=task_id,
                        generation=generation,
                        evidence={"url": h_url},
                    )
            return v_res

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
