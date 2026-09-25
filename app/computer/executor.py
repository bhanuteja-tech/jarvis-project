"""ComputerAgent — Plan → Act → Observe → Verify execution loop.

This is the central execution engine for computer-control tasks.  It:

1. PLAN:    ComputerIntentExtractor → ReferenceResolver → SemanticTaskPlanner
2. ACT:     Dispatches each TaskStep to AgentHarness (existing tool dispatch)
3. OBSERVE: Calls ComputerObserver.observe() after each step
4. VERIFY:  Uses VerificationService to check postconditions
5. RESPOND: TruthfulResponseGenerator generates the final response

Strict rules:
- NEVER claim success unless VerificationResult.verified is True
- NEVER expose PII in events, narration, or logs
- One active run per session; new run cancels previous
- Career pipeline (Phases 1-6) is NEVER touched or called
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agent.task_manager import TaskLifecycle, default_task_manager
from app.computer.intent_extractor import ComputerIntentExtractor, default_extractor
from app.computer.reference_resolver import ReferenceResolver, default_resolver
from app.computer.response_generator import (
    ExecutionResult,
    TruthfulResponseGenerator,
    default_response_generator,
)
from app.computer.semantic_planner import (
    SemanticTaskPlanner,
    TaskPlan,
    TaskStep,
    VerificationStrategy,
    default_planner,
)
from app.computer.web_context_tracker import WebContextTracker, default_web_context_tracker
from app.desktop.observer import ComputerObserver, default_observer
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.verifier import VerificationResult, VerificationService, default_verifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent events (yielded to orchestrator for WebSocket streaming)
# ---------------------------------------------------------------------------

def _make_agent_event(event_type: str, **data: Any) -> dict[str, Any]:
    """Build a typed event dict for WebSocket streaming."""
    return {
        "agent_event_type": event_type,
        "ts": time.time(),
        **data,
    }


# ---------------------------------------------------------------------------
# Tool → AgentHarness dispatch
# ---------------------------------------------------------------------------

class HarnessDispatcher:
    """Dispatches TaskSteps to AgentHarness. Returns raw harness result dict."""


    def __init__(self, harness: Any | None = None) -> None:
        self._harness = harness

    def _get_harness(self) -> Any:
        if self._harness is not None:
            return self._harness
        from app.desktop.agent_harness import default_harness
        return default_harness

    def dispatch(
        self,
        step: TaskStep,
        computer_state: ComputerState,
        session: Any | None = None,
    ) -> dict[str, Any]:
        """Dispatch a TaskStep to the AgentHarness. Returns raw harness result."""
        from app.routing.taxonomy import Intent

        harness = self._get_harness()
        tool = step.tool
        params = dict(step.params)

        logger.info("Dispatching tool=%s params=%s", tool, list(params.keys()))

        action_intent: Any = None
        cmd_params: dict[str, Any] = {}

        if tool == "open_application":
            action_intent = Intent.OPEN_APPLICATION
            cmd_params = {
                "application": params.get("app_name") or params.get("application") or "",
                "app_name": params.get("app_name") or params.get("application") or "",
            }

        elif tool == "close_application":
            action_intent = Intent.CLOSE_APPLICATION
            cmd_params = {
                "application": params.get("app_name") or params.get("application") or "",
            }

        elif tool in ("focus_application", "focus_browser"):
            action_intent = Intent.FOCUS_APPLICATION
            cmd_params = {
                "application": params.get("app_name") or params.get("browser_name") or "",
            }

        elif tool == "open_browser":
            action_intent = Intent.BROWSER_OPEN
            cmd_params = {
                "url": params.get("url"),
                "browser_name": params.get("browser_name", "google_chrome"),
            }

        elif tool in ("navigate_browser", "navigate"):
            action_intent = Intent.BROWSER_NAVIGATE
            svc = (params.get("service_name") or params.get("service") or "").lower()
            is_acc = params.get("account", True if svc == "github" else False)
            cmd_params = {
                "url": params.get("url", ""),
                "service": svc,
                "service_name": svc,
                "query": params.get("query"),
                "browser_name": params.get("browser_name"),
                "account": is_acc,
            }

        elif tool in ("search_browser", "browser_search"):
            action_intent = Intent.BROWSER_SEARCH
            cmd_params = {
                "query": params.get("query", ""),
                "service": params.get("service_name") or params.get("service") or "google",
                "browser_name": params.get("browser_name"),
            }

        elif tool == "prepare_message":
            action_intent = Intent.MESSAGING_SEND
            cmd_params = {
                "recipient": params.get("recipient", ""),
                "message": params.get("message_text") or params.get("message", ""),
            }

        elif tool == "execute_confirmed_send":
            action_intent = Intent.CONFIRM_ACTION
            cmd_params = {}

        elif tool == "take_screenshot":
            action_intent = Intent.SCREEN_ANALYZE
            cmd_params = {}

        elif tool == "open_file":
            action_intent = Intent.OPEN_FILE
            cmd_params = params

        elif tool in ("open_folder", "navigate_folder"):
            action_intent = Intent.OPEN_FOLDER
            cmd_params = params

        elif tool in ("count_directory_items", "count_items"):
            action_intent = "count_directory_items"
            cmd_params = params

        elif tool == "list_files":
            action_intent = Intent.LIST_FILES
            cmd_params = params

        elif tool == "search_files":
            action_intent = Intent.SEARCH_FILES
            cmd_params = params

        elif tool in ("select_item", "open_item"):
            action_intent = "select_item"
            cmd_params = params

        elif tool in ("scroll_page", "scroll"):
            action_intent = "scroll"
            cmd_params = params

        elif tool in ("click_element", "click"):
            action_intent = "click"
            cmd_params = params

        elif tool == "computer_control_fallback":
            action_intent = params.get("intent", Intent.BROWSER_OPEN)
            cmd_params = params

        else:
            action_intent = tool
            cmd_params = params

        try:
            res = harness.execute_command(action_intent, cmd_params, session=session)
            if hasattr(res, "to_dict"):
                result_dict = res.to_dict()
            elif isinstance(res, dict):
                result_dict = res
            else:
                result_dict = {"success": True, "message": str(res)}

            # Sync session state if present
            if session is not None:
                if result_dict.get("needs_user_input") and result_dict.get("pending_prompt"):
                    session.pending_prompt = result_dict["pending_prompt"]
                browser_actions = (
                    "open_app", "open_browser", "open_url", "search_web", "open_service"
                )
                if (
                    result_dict.get("action") in browser_actions
                    or cmd_params.get("browser_name")
                ):
                    session.active_browser = True

            # Update computer_state URL tracking
            if cmd_params.get("url"):
                computer_state.current_url = cmd_params["url"]
                computer_state.active_page_url = cmd_params["url"]
            if result_dict.get("details") and result_dict["details"].get("url"):
                computer_state.current_url = result_dict["details"]["url"]
                computer_state.active_page_url = result_dict["details"]["url"]

            return result_dict
        except Exception as exc:
            logger.exception("Error executing command %s: %s", action_intent, exc)
            return {"success": False, "message": str(exc), "error": str(exc)}



# ---------------------------------------------------------------------------
# ComputerAgent
# ---------------------------------------------------------------------------

class ComputerAgent:
    """Plan → Act → Observe → Verify agent for desktop computer control.

    Usage:
        agent = ComputerAgent()
        async for event in agent.run(text, session=session):
            yield event_to_ws(event)
    """

    def __init__(
        self,
        extractor: ComputerIntentExtractor | None = None,
        planner: SemanticTaskPlanner | None = None,
        resolver: ReferenceResolver | None = None,
        observer: ComputerObserver | None = None,
        verifier: VerificationService | None = None,
        response_gen: TruthfulResponseGenerator | None = None,
        web_tracker: WebContextTracker | None = None,
        state: ComputerState | None = None,
        dispatcher: HarnessDispatcher | None = None,
    ) -> None:
        self._extractor = extractor or default_extractor
        self._planner = planner or default_planner
        self._resolver = resolver or default_resolver
        self._observer = observer or default_observer
        self._verifier = verifier or default_verifier
        self._response_gen = response_gen or default_response_generator
        self._web_tracker = web_tracker or default_web_context_tracker
        self._state = state or default_computer_state
        self._dispatcher = dispatcher or HarnessDispatcher()

    # ------------------------------------------------------------------
    async def run(
        self,
        text: str,
        *,
        is_voice: bool = False,
        session: Any | None = None,
        generation: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute the full Plan→Act→Observe→Verify loop and yield events.

        This is an async generator. The orchestrator iterates over it
        and converts events to WebSocket envelopes.
        """
        # Task lifecycle & generation management
        task_gen = generation if generation is not None else default_task_manager.current_generation
        task = default_task_manager.create_task(intent=text, generation=task_gen)
        self._state.current_generation = task_gen
        self._state.current_task_id = task.task_id

        # --- Phase 1: PLAN ---
        yield _make_agent_event("plan_start", text=text, task_id=task.task_id, generation=task_gen)

        task.transition_to(TaskLifecycle.PLANNING)
        try:
            intent = self._extractor.extract(text, self._state)
            plan = await self._build_plan(text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ComputerAgent planning failed: %s", exc)
            task.fail(str(exc))
            yield _make_agent_event("error", message=f"Planning failed: {exc}", task_id=task.task_id)
            return

        # Structured Debug Telemetry
        target_repr = (
            intent.target
            or (intent.application.canonical if intent.application else "")
            or (intent.destination.site if intent.destination else "")
        )
        logger.info(
            "[TELEMETRY] REQUEST: '%s' | NORMALIZED: '%s' | INTENT: %s | TARGET: '%s' | CONTEXT BEFORE: app=%s dir=%s site=%s page=%s | GEN: %d",
            text,
            intent.raw_text,
            intent.intent_type,
            target_repr,
            self._state.active_application,
            self._state.current_directory,
            self._state.web_context.site,
            self._state.web_context.page,
            task_gen,
        )

        # Check for generation invalidation / stale task
        if task.is_stale() or not default_task_manager.is_generation_valid(task_gen):
            logger.warning("[TELEMETRY] Task %s (gen %d) is stale after planning; aborting", task.task_id, task_gen)
            return

        if plan.requires_resolution:
            # Cannot proceed — ask user for clarification
            prompt = plan.resolution_error or intent.clarification_prompt or "I need to know what you want me to open. Could you specify?"
            task.complete({"status": "clarification_required", "prompt": prompt})
            logger.info("[TELEMETRY] CLARIFICATION PROMPT: %s", prompt)
            yield _make_agent_event("response", text=prompt, verified=False, task_id=task.task_id)
            return

        yield _make_agent_event(
            "plan_ready",
            description=plan.description,
            steps=[s.description for s in plan.steps],
            step_count=len(plan.steps),
            task_id=task.task_id,
            generation=task_gen,
        )

        # --- Phase 2-4: ACT → OBSERVE → VERIFY (per step) ---
        step_results: list[dict[str, Any]] = []

        for i, step in enumerate(plan.steps):
            if task.is_stale() or not default_task_manager.is_generation_valid(task_gen):
                logger.warning("[TELEMETRY] Task %s is stale at step %d; aborting", task.task_id, i)
                return

            task.current_step = i + 1
            task.transition_to(TaskLifecycle.ACTING)

            # Announce step start
            yield _make_agent_event(
                "step_start",
                step_id=step.step_id,
                step_idx=i,
                total_steps=len(plan.steps),
                description=step.description,
                tool=step.tool,
                task_id=task.task_id,
                generation=task_gen,
            )

            # High-risk steps need user confirmation
            if step.is_high_risk:
                yield _make_agent_event(
                    "needs_confirm",
                    step_id=step.step_id,
                    description=step.description,
                    params={k: v for k, v in step.params.items() if k != "message_text"},
                    task_id=task.task_id,
                )
                harness_result = self._act(step, session=session)
                yield _make_agent_event(
                    "step_done",
                    step_id=step.step_id,
                    tool=step.tool,
                    success=harness_result.get("success", False),
                    verified=None,
                    description=step.description,
                    message=harness_result.get("message", ""),
                    needs_user_input=True,
                    task_id=task.task_id,
                )
                response_text = harness_result.get("message", "")
                yield _make_agent_event(
                    "response", text=response_text, verified=None, needs_confirm=True, task_id=task.task_id
                )
                return

            # ACT
            harness_result = self._act(step, session=session)

            if task.is_stale() or not default_task_manager.is_generation_valid(task_gen):
                logger.warning("[TELEMETRY] Task %s is stale after ACT; aborting", task.task_id)
                return

            # Check if interactive user input needed
            if harness_result.get("needs_user_input"):
                yield _make_agent_event(
                    "needs_input",
                    step_id=step.step_id,
                    description=step.description,
                    pending_prompt=harness_result.get("pending_prompt"),
                    message=harness_result.get("message", ""),
                    task_id=task.task_id,
                )
                yield _make_agent_event(
                    "response",
                    text=harness_result.get("message", ""),
                    verified=None,
                    needs_user_input=True,
                    task_id=task.task_id,
                )
                return

            # OBSERVE (brief delay to allow OS/window update)
            task.transition_to(TaskLifecycle.OBSERVING)
            await asyncio.sleep(0.1)
            observation = self._observe()

            # Update web context from observation and harness result
            self._update_web_context(observation, step, harness_result)

            # VERIFY
            task.transition_to(TaskLifecycle.VERIFYING)
            verification = self._verify(step, harness_result, observation, task_id=task.task_id, generation=task_gen)

            # STATE COMMIT: Authoritative state commit ONLY after verification
            verified_state = verification.to_verified_state(
                action=step.tool,
                target=step.verification_target or "",
                verified_app=observation.get("active_application"),
                verified_directory=observation.get("current_directory"),
                verified_url=(observation.get("browser") or {}).get("url") or harness_result.get("details", {}).get("url"),
                verified_page=self._state.web_context.page,
                verified_items=observation.get("observed_items") or harness_result.get("details", {}).get("items") or None,
            )
            state_committed = self._state.commit_verified_state(verified_state)
            self._update_state(step, harness_result, verification)

            logger.info(
                "[TELEMETRY] STEP %d: TOOL=%s | ACTION=%s | OBSERVED: app=%s dir=%s | VERIFIED=%s ('%s') | STATE COMMITTED=%s",
                i,
                step.tool,
                harness_result.get("action"),
                observation.get("active_application"),
                observation.get("current_directory"),
                verification.verified,
                verification.reason,
                state_committed,
            )

            # Record result
            step_result = {
                "step_id": step.step_id,
                "tool": step.tool,
                "description": step.description,
                "success": harness_result.get("success", False),
                "verified": verification.verified,
                "confidence": verification.confidence,
                "reason": verification.reason,
                "harness_message": harness_result.get("message", ""),
            }
            step_results.append(step_result)

            if verification.verified:
                yield _make_agent_event(
                    "step_done",
                    computer_state=self._state.to_dict(),
                    web_context=self._state.web_context.to_dict(),
                    task_id=task.task_id,
                    generation=task_gen,
                    **step_result,
                )
            else:
                yield _make_agent_event(
                    "step_failed",
                    computer_state=self._state.to_dict(),
                    web_context=self._state.web_context.to_dict(),
                    task_id=task.task_id,
                    generation=task_gen,
                    **step_result,
                )
                # Fail fast on a failed step in a multi-step plan
                if step.requires_previous and i > 0:
                    yield _make_agent_event(
                        "response",
                        text=self._response_gen.generate(
                            ExecutionResult(
                                success=False,
                                verified=False,
                                action=step.tool,
                                intent_description=step.description,
                                message=harness_result.get("message", ""),
                                reason=verification.reason,
                                verify_method=verification.details.get("method"),
                            ),
                            is_voice=is_voice,
                        ),
                        verified=False,
                        computer_state=self._state.to_dict(),
                        web_context=self._state.web_context.to_dict(),
                        task_id=task.task_id,
                    )
                    return

        # --- Phase 5: RESPOND ---
        if task.is_stale() or not default_task_manager.is_generation_valid(task_gen):
            logger.warning("[TELEMETRY] Task %s is stale before response; aborting response emission", task.task_id)
            return

        overall_success = all(r.get("verified") for r in step_results)
        last_step = step_results[-1] if step_results else {}
        last_harness_msg = last_step.get("harness_message", "")

        final_result = ExecutionResult(
            success=overall_success,
            verified=overall_success,
            action=plan.steps[-1].tool if plan.steps else "unknown",
            intent_description=plan.description,
            message=last_harness_msg,
            reason=last_step.get("reason"),
            verify_method=last_step.get("reason"),
            steps=step_results,
        )

        if overall_success and last_harness_msg and len(plan.steps) == 1:
            response_text = last_harness_msg
        else:
            response_text = self._response_gen.generate(final_result, is_voice=is_voice)

        task.complete({"status": "success", "steps": step_results, "response": response_text})
        logger.info("[TELEMETRY] RESPONSE: '%s' | OVERALL VERIFIED=%s", response_text, overall_success)

        yield _make_agent_event(
            "response",
            text=response_text,
            verified=overall_success,
            step_results=step_results,
            plan_description=plan.description,
            computer_state=self._state.to_dict(),
            web_context=self._state.web_context.to_dict(),
            task_id=task.task_id,
            generation=task_gen,
        )

    # ------------------------------------------------------------------
    async def _build_plan(self, text: str) -> TaskPlan:
        """Extract intent, resolve references, and build the task plan."""
        # 1. Extract intent (sync; fast for deterministic path)
        intent = self._extractor.extract(text, self._state)
        logger.info(
            "Intent extracted: type=%s confidence=%.2f method=%s",
            intent.intent_type,
            intent.confidence,
            intent.extraction_method,
        )

        # 2. Resolve references if needed
        refs = self._resolver.resolve_all(text, self._state)
        for ref in refs:
            if ref.resolved:
                logger.info("Reference resolved: kind=%s value=%s", ref.kind, ref.value)

        # 3. Plan
        plan = self._planner.plan(intent, self._state)
        return plan

    # ------------------------------------------------------------------
    def _act(self, step: TaskStep, session: Any | None = None) -> dict[str, Any]:
        """Execute a TaskStep via HarnessDispatcher. Catches all exceptions."""
        try:
            result = self._dispatcher.dispatch(step, self._state, session=session)
            logger.info("ACT %s → success=%s", step.tool, result.get("success"))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool dispatch failed for %s: %s", step.tool, exc)
            return {
                "success": False,
                "message": f"Tool dispatch error: {exc}",
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    def _observe(self) -> dict[str, Any]:
        """Take a ground-truth OS observation."""
        try:
            return self._observer.observe()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Observation failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    def _verify(
        self,
        step: TaskStep,
        harness_result: dict[str, Any],
        observation: dict[str, Any],
        task_id: str | None = None,
        generation: int = 0,
    ) -> VerificationResult:
        """Verify the step postcondition using the VerificationService."""
        strategy = step.verification
        target = step.verification_target

        try:
            if step.tool in ("count_directory_items", "count_items"):
                details = harness_result.get("details") or {}
                raw_count = details.get("count", 0)
                if isinstance(raw_count, dict):
                    raw_count = raw_count.get("count", 0)
                try:
                    count_val = int(raw_count)
                except (ValueError, TypeError):
                    count_val = 0
                return self._verifier.verify_item_count(
                    expected_target=step.params.get("target", "desktop"),
                    count=count_val,
                    observation=observation,
                    task_id=task_id,
                    generation=generation,
                )

            if step.expected_state_updates.get("web_context.page") == "home":
                svc = step.expected_state_updates.get("web_context.site") or "youtube"
                return self._verifier.verify_site_home(
                    domain_or_site=svc,
                    observation=observation,
                    task_id=task_id,
                    generation=generation,
                )

            if strategy == VerificationStrategy.NONE:
                # No verification — trust harness result (cautious)
                ok = harness_result.get("success", False)
                return VerificationResult(
                    success=ok,
                    confidence=0.50 if ok else 0.10,
                    reason="no verification strategy configured",
                    details={"method": "none"},
                    task_id=task_id,
                    generation=generation,
                    expected=step.description,
                    observed="completed" if ok else "failed",
                    evidence={"harness_result": harness_result},
                )

            if strategy == VerificationStrategy.WINDOW_FOREGROUND:
                return self._verifier.verify_application_opened(
                    target or "",
                    observation,
                    task_id=task_id,
                    generation=generation,
                )

            if strategy == VerificationStrategy.BROWSER_FOREGROUND:
                return self._verifier.verify_browser_foreground(
                    target or "google_chrome",
                    observation,
                )

            if strategy == VerificationStrategy.URL_TITLE_POLL:
                # Use live window controller for polling
                from app.desktop.window_controller import default_window_controller
                return self._verifier.verify_navigation_by_title(
                    target or "",
                    observation,
                    poll_window_controller=default_window_controller,
                    poll_seconds=3.0,
                )

            if strategy == VerificationStrategy.FILESYSTEM_DIRECTORY:
                return self._verifier.verify_folder_opened(
                    target or "",
                    observation,
                    task_id=task_id,
                    generation=generation,
                )

            if strategy == VerificationStrategy.SEARCH_URL:
                return self._verifier.verify_search_results(
                    target or "",
                    observation,
                    task_id=task_id,
                    generation=generation,
                )

            if strategy == VerificationStrategy.WINDOW_CONTENT:
                return self._verifier.verify_application_opened(
                    target or "",
                    observation,
                    task_id=task_id,
                    generation=generation,
                )

            if strategy == VerificationStrategy.CONFIRMATION_REQUIRED:
                # Not a verification — will be handled by needs_confirm flow
                return VerificationResult(
                    success=harness_result.get("success", False),
                    confidence=0.90,
                    reason="confirmation required from user",
                    details={"method": "confirmation"},
                    task_id=task_id,
                    generation=generation,
                )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Verification failed for strategy=%s: %s", strategy, exc)
            return VerificationResult(
                success=False,
                confidence=0.0,
                reason=f"verification error: {exc}",
                details={"method": str(strategy)},
                task_id=task_id,
                generation=generation,
            )

        return VerificationResult(
            success=False,
            confidence=0.0,
            reason=f"unknown verification strategy: {strategy}",
            details={},
            task_id=task_id,
            generation=generation,
        )

    # ------------------------------------------------------------------
    def _update_web_context(
        self,
        observation: dict[str, Any],
        step: TaskStep,
        harness_result: dict[str, Any] | None = None,
    ) -> None:
        """Update web context from the post-step observation or harness details."""
        browser_info = observation.get("browser") or {}
        h_details = (harness_result or {}).get("details", {})
        url = (
            browser_info.get("url")
            or h_details.get("url")
            or (harness_result or {}).get("url")
            or step.params.get("url")
            or ""
        )
        title = (
            observation.get("active_window_title")
            or h_details.get("title")
            or ""
        )

        if url:
            self._web_tracker.update_from_navigation(url, title)
        elif title:
            self._web_tracker.infer_from_title(title)

        svc = step.params.get("service") or step.params.get("service_name")
        if svc and not self._state.web_context.site:
            svc_clean = str(svc).lower()
            self._state.web_context.site = svc_clean
            if svc_clean == "youtube":
                self._state.web_context.domain = "youtube.com"
                if not self._state.web_context.page:
                    self._state.web_context.page = "home"

    # ------------------------------------------------------------------
    def _update_state(
        self,
        step: TaskStep,
        harness_result: dict[str, Any],
        verification: VerificationResult,
    ) -> None:
        """Apply expected state updates from a completed step."""
        self._state.last_verified = verification.verified
        self._state.last_verify_method = verification.details.get("method", str(step.verification))
        self._state.last_action = step.tool
        self._state.last_action_result = harness_result

        # Apply explicit state updates from plan
        for key, value in step.expected_state_updates.items():
            if "." in key:
                # Nested key: e.g. "web_context.site"
                obj_key, attr = key.split(".", 1)
                obj = getattr(self._state, obj_key, None)
                if obj is not None and hasattr(obj, attr):
                    val_to_set = value.lower() if isinstance(value, str) and attr == "site" else value
                    setattr(obj, attr, val_to_set)
                    if attr == "site" and val_to_set == "youtube" and not getattr(obj, "domain", None):
                        obj.domain = "youtube.com"
            elif hasattr(self._state, key):
                setattr(self._state, key, value)

        course_name = step.expected_state_updates.get("web_context.course")
        if course_name:
            self._web_tracker.update_course(course_name)

        channel_name = step.expected_state_updates.get("web_context.channel")
        if channel_name:
            self._web_tracker.update_channel(channel_name)


# ---------------------------------------------------------------------------
# Singleton for orchestrator use
# ---------------------------------------------------------------------------

default_computer_agent = ComputerAgent()

__all__ = ["ComputerAgent", "HarnessDispatcher", "default_computer_agent"]
