"""Jarvis orchestrator: intent -> plan -> execute -> narrate.

A thin orchestration layer around the frozen compiled LangGraph workflow.
Each user message yields at most one deterministic plan. The graph is the
only execution engine; the orchestrator never duplicates Phase 1–6 logic.

Streaming contract:
- workflow progress comes from ``graph.astream(state, stream_mode="updates")``
  (one update per completed node);
- agent status events wrap each phase;
- the final deterministic reply is sent as one ``assistant_message`` (no fake
  token streaming; ``token`` events only exist when a real streaming LLM
  provider is enabled later).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.candidate.analyzer import ResumeAnalyzer
from app.config.settings import Settings
from app.jarvis import events as ev
from app.jarvis.intent import Plan, parse_intent
from app.jarvis.narrator import narrate
from app.jarvis.sessions import InMemorySessionStore, Session

logger = logging.getLogger(__name__)

Sender = Callable[[dict[str, Any]], Awaitable[None]]


class EventEmitter:
    """Monotonic-seq envelope sender bound to one connection."""

    def __init__(self, send: Sender) -> None:
        self._send = send
        self._seq = 0

    async def emit(self, event_type: ev.EventType | str, run_id: str | None = None, **data: Any) -> dict:
        self._seq += 1
        envelope = ev.make_event(event_type, seq=self._seq, run_id=run_id, **data)
        await self._send(envelope)
        return envelope


def default_adapters(settings: Settings) -> list[Any]:
    """Composition root for source adapters (frozen clients, read-only use)."""
    from app.sources.greenhouse.client import GreenhouseClient
    from app.sources.greenhouse.adapter import GreenhouseAdapter
    from app.sources.lever.client import LeverClient
    from app.sources.lever.adapter import LeverAdapter

    adapters: list[Any] = [
        GreenhouseAdapter(GreenhouseClient(settings)),
        LeverAdapter(LeverClient(settings)),
    ]
    if settings.searchapi_api_key.get_secret_value().strip():
        from app.sources.searchapi.jobs_adapter import SearchApiJobsAdapter
        from app.sources.searchapi.client import SearchApiClient

        adapters.append(SearchApiJobsAdapter(SearchApiClient(settings)))
    return adapters


class JarvisOrchestrator:
    def __init__(
        self,
        settings: Settings,
        *,
        session_store: InMemorySessionStore,
        graph_factory: Callable[[], Any] | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._sessions = session_store
        self._llm = llm_client if settings.jarvis_assistant_llm_enabled else None
        self._graph_factory = graph_factory or self._default_graph_factory
        self._current_task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(
            max(1, getattr(settings, "jarvis_max_concurrent_runs", 4))
        )

    @staticmethod
    def _default_graph_factory(settings: Settings):
        def factory() -> Any:
            from app.graph.workflow import build_workflow

            return build_workflow(default_adapters(settings))

        return factory

    # ------------------------------------------------------------------
    async def handle_message(
        self,
        session: Session,
        message: Mapping[str, Any],
        *,
        send: Sender,
    ) -> None:
        emitter = EventEmitter(send)
        message_type = str(message.get("type") or "chat")

        if message_type == "cancel":
            await self._cancel(emitter)
            return

        if message_type == "resume_upload":
            await self._handle_resume_upload(session, message, emitter)
            return

        if message_type == "chat":
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                await emitter.emit(ev.EventType.ERROR, message="empty message")
                return
            plan = parse_intent(text)

            # Cancel any in-flight run: one active run per connection.
            await self._cancel(emitter, quiet=True)

            run_id = f"run_{session.session_id[:8]}_{int(time.time() * 1000)}"
            await emitter.emit(
                ev.EventType.AGENT_STARTED, run_id=run_id,
                action=plan.action, params=_safe_params(plan.params),
            )

            if plan.action == "help":
                from app.jarvis.intent import GRAMMAR_HELP

                await self._speak(emitter, run_id, GRAMMAR_HELP)
                await emitter.emit(ev.EventType.AGENT_COMPLETED, run_id=run_id)
                return

            if plan.action == "get_results":
                reply, attachments = narrate(session.last_state)
                await self._speak(emitter, run_id, reply, attachments)
                await emitter.emit(ev.EventType.COMPLETED, run_id=run_id)
                return

            if plan.action == "select_target":
                index = plan.params.get("target_job_index")
                prefs = _prefs_with_target(session.last_state, index)
                if prefs is None and index is not None:
                    prefs = {"tailoring": {"target_job_index": index}}
                    if isinstance(session.last_state, dict):
                        merged = dict(session.last_state.get("search_preferences") or {})
                        merged.update({"tailoring": prefs["tailoring"]})
                        prefs = merged
                await emitter.emit(
                    ev.EventType.AGENT_THINKING, run_id=run_id,
                    detail="re-running pipeline with explicit target",
                )
                await self._run_discovery(
                    session, emitter, run_id,
                    user_params={"user_query": _last_query(session)},
                    pref_overrides=prefs or {},
                    select_hint=plan.reply_hint,
                )
                return

            if plan.action == "run_discovery":
                await emitter.emit(
                    ev.EventType.AGENT_THINKING, run_id=run_id,
                    detail="planning job discovery",
                )
                await self._run_discovery(
                    session, emitter, run_id, user_params=plan.params,
                    pref_overrides={},
                    select_hint=plan.reply_hint,
                )
                return

            await emitter.emit(
                ev.EventType.ERROR, code="unknown_action",
                message=f"unsupported action {plan.action}",
            )

    # ------------------------------------------------------------------
    async def _handle_resume_upload(
        self,
        session: Session,
        message: Mapping[str, Any],
        emitter: EventEmitter,
    ) -> None:
        content = message.get("content")
        name = str(message.get("name") or "resume.txt")
        if (
            not isinstance(content, str)
            or not content.strip()
            or len(content) > self._settings.candidate_max_chars
        ):
            await emitter.emit(
                ev.EventType.ERROR,
                code="invalid_resume",
                message="resume must be non-empty plain text within the size limit",
            )
            return
        lowered = name.lower()
        if not lowered.endswith((".txt", ".md")) and message.get("explicit_text") is not True:
            await emitter.emit(
                ev.EventType.ERROR,
                code="unsupported_format",
                message="only .txt/.md resumes are supported (PDF/DOCX unsupported)",
            )
            return

        analyzer = ResumeAnalyzer(self._settings)
        result = await analyzer.build_profile({"text": content})

        if result.status in {"FAILED", "SKIPPED"}:
            await emitter.emit(
                ev.EventType.ERROR,
                code=result.reason or "resume_failed",
                message="resume could not be parsed",
            )
            return

        session.candidate_input = {"text": content}
        skills = {skill.name for skill in (result.profile.skills.items if result.profile else [])}
        await emitter.emit(
            ev.EventType.TOOL_COMPLETED,
            tool="set_resume",
            status=result.status.value if hasattr(result.status, "value") else result.status,
            skills_found=len(skills),
            experience_items=len(result.profile.experience.items) if result.profile else 0,
        )
        await self._speak(
            emitter,
            None,
            f"Resume stored ({len(skills)} skills detected). "
            "Now say e.g. 'find python engineer in berlin'.",
        )

    # ------------------------------------------------------------------
    async def _run_discovery(
        self,
        session: Session,
        emitter: EventEmitter,
        run_id: str,
        *,
        user_params: Mapping[str, Any],
        pref_overrides: Mapping[str, Any],
        select_hint: str | None,
    ) -> None:
        if self._current_task is not None and not self._current_task.done():
            self._current_task.cancel()

        state: dict[str, Any] = {
            "user_query": user_params.get("user_query"),
            "search_preferences": {
                **pref_overrides,
                **({"locations": user_params["locations"]}
                   if user_params.get("locations") else {}),
            },
        }
        if session.candidate_input is not None:
            state["candidate_input"] = session.candidate_input

        semaphore = self._semaphore
        graph = self._graph_factory()
        final_state: dict[str, Any] = dict(state)

        async with semaphore:
            task = asyncio.current_task()
            self._current_task = task
            try:
                async for update in graph.astream(state, stream_mode="updates"):
                    for node_name, node_update in update.items():
                        if not isinstance(node_update, dict):
                            continue
                        _merge(final_state, node_update)
                        await emitter.emit(
                            ev.EventType.WORKFLOW_NODE_COMPLETED,
                            run_id=run_id,
                            node=node_name,
                            keys=sorted(node_update.keys()),
                        )
            except asyncio.CancelledError:
                await emitter.emit(ev.EventType.RUN_CANCELLED, run_id=run_id)
                raise
            finally:
                if self._current_task is task:
                    self._current_task = None

        session.last_state = final_state
        reply, attachments = narrate(final_state)
        if select_hint:
            reply = f"{select_hint}\n{reply}"
        session.append_message("assistant", reply)

        await self._speak(emitter, run_id, reply, attachments)
        await emitter.emit(ev.EventType.COMPLETED, run_id=run_id)

    async def _cancel(self, emitter: EventEmitter, *, quiet: bool = False) -> None:
        task = self._current_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            if not quiet:
                await emitter.emit(ev.EventType.RUN_CANCELLED)
        self._current_task = None

    async def _speak(
        self,
        emitter: EventEmitter,
        run_id: str | None,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        await emitter.emit(ev.EventType.AGENT_SPEAKING if hasattr(ev.EventType, "AGENT_SPEAKING") else "agent_speaking", run_id=run_id)
        await emitter.emit(
            ev.EventType.ASSISTANT_MESSAGE,
            run_id=run_id,
            text=text,
            attachments=attachments or [],
        )


def _safe_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items()}


def _prefs_with_target(state: Mapping[str, Any] | None, index: int | None) -> dict | None:
    if state is None or index is None:
        return None
    prefs = dict(state.get("search_preferences") or {})
    tailoring = dict(prefs.get("tailoring") or {})
    tailoring["target_job_index"] = index
    prefs["tailoring"] = tailoring
    return prefs


def _last_query(session: Session) -> str:
    for message in reversed(session.messages):
        if message.get("role") == "user":
            return str(message.get("text") or "")
    return "python engineer"


def _merge(target: dict[str, Any], update: Mapping[str, Any]) -> None:
    target.update(update)


__all__ = ["EventEmitter", "JarvisOrchestrator", "default_adapters"]
