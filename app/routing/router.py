"""Priority-Based Intent and Entity Router for JARVIS.

Disambiguates computer control, browser navigation, filesystem search, and career
intelligence requests. Enforces strict isolation so computer tasks never accidentally
enter the career graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.desktop.web_services import find_service
from app.routing.app_resolver import ApplicationResolver
from app.routing.normalizer import normalize_speech
from app.routing.planner import ExecutionPlan, ExecutionPlanner, PlannedStep
from app.routing.taxonomy import Intent

# Explicit career cue words that MUST be present to route to career workflows
CAREER_KEYWORDS_RE = re.compile(
    r"\b(?:jobs?|internships?|roles?|positions?|openings?|vacanc(?:y|ies)|hiring\s+for|employment\s+opportunities)\b",
    re.IGNORECASE,
)

# Services recognized for browser search
BROWSER_SERVICE_NAMES = {
    "youtube",
    "yt",
    "google",
    "github",
    "gh",
    "reddit",
    "amazon",
    "spotify",
    "hackernews",
    "hn",
    "wikipedia",
    "wiki",
    "stackoverflow",
}


_ACTION_MAP: dict[Intent, str] = {
    Intent.OPEN_APPLICATION: "open_app",
    Intent.CLOSE_APPLICATION: "close_app",
    Intent.FOCUS_APPLICATION: "focus_app",
    Intent.OPEN_FOLDER: "open_folder",
    Intent.NAVIGATE_FOLDER: "open_folder",
    Intent.LIST_FILES: "list_files",
    Intent.SEARCH_FILES: "search_files",
    Intent.OPEN_FILE: "open_file",
    Intent.BROWSER_OPEN: "open_browser",
    Intent.BROWSER_NAVIGATE: "open_url",
    Intent.BROWSER_SEARCH: "search_web",
    Intent.BROWSER_BACK: "navigate_back",
    Intent.BROWSER_FORWARD: "navigate_forward",
    Intent.SCREEN_READ: "screenshot",
    Intent.SCREEN_ANALYZE: "screenshot",
    Intent.MESSAGING_SEND: "send_message",
    Intent.CONFIRM_ACTION: "confirm_action",
    Intent.REJECT_ACTION: "reject_action",
}


@dataclass(frozen=True)
class RouteResult:
    """Authoritative routing result including intent, entities, plan, and diagnostics."""

    intent: Intent
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    normalized_text: str = ""
    is_correction: bool = False
    is_compound: bool = False
    plan: ExecutionPlan | None = None
    entity: str | None = None
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": str(self.intent),
            "params": self.params,
            "confidence": self.confidence,
            "normalized_text": self.normalized_text,
            "is_correction": self.is_correction,
            "is_compound": self.is_compound,
            "plan": self.plan.to_dict() if self.plan else None,
            "entity": self.entity,
            "target": self.target,
        }


class IntentRouter:
    """Authoritative deterministic priority router."""

    def __init__(
        self,
        app_resolver: ApplicationResolver | None = None,
        planner: ExecutionPlanner | None = None,
    ) -> None:
        self.app_resolver = app_resolver or ApplicationResolver()
        self.planner = planner or ExecutionPlanner()

    def route(self, text: str, context: Any | None = None) -> RouteResult:
        """Route a user utterance with full normalization, planning, and disambiguation."""
        # 1. Speech Normalization & Correction Extraction
        norm = normalize_speech(text)
        cleaned = norm.cleaned_text
        lowered = cleaned.lower()

        if not cleaned:
            return RouteResult(
                intent=Intent.GENERAL_CONVERSATION,
                normalized_text="",
                is_correction=norm.is_correction,
            )

        # 2. Session Control / Interrupt / Confirmations
        if lowered in {
            "bye jarvis",
            "goodbye jarvis",
            "bye",
            "goodbye",
            "stop listening",
            "end voice session",
            "end session",
            "terminate session",
            "exit voice",
        }:
            return RouteResult(
                intent=Intent.VOICE_SESSION_STOP,
                normalized_text=cleaned,
                is_correction=norm.is_correction,
            )

        if lowered in {"stop", "cancel", "actually stop", "interrupt", "hold on", "pause"}:
            return RouteResult(
                intent=Intent.INTERRUPT,
                normalized_text=cleaned,
                is_correction=norm.is_correction,
            )

        if lowered in {"start voice session", "start voice", "listen continuously"}:
            return RouteResult(
                intent=Intent.VOICE_SESSION_START,
                normalized_text=cleaned,
                is_correction=norm.is_correction,
            )

        # Confirmation / Rejection for high-impact side effects
        if re.match(
            r"^(?:yes(?:,\s*|\s+)?(?:send\s+it|please|do\s+it|confirm|proceed|go\s+ahead)?|send\s+it|confirm|proceed|go\s+ahead|sure|yes)$",
            cleaned,
            re.IGNORECASE,
        ):
            return RouteResult(
                intent=Intent.CONFIRM_ACTION,
                params={"confirmed": True},
                normalized_text=cleaned,
            )

        if re.match(
            r"^(?:no(?:,\s*|\s+)?(?:don't\s+send|cancel|abort)?|don't\s+send(?:\s+it)?|cancel\s+that|abort|no)$",
            cleaned,
            re.IGNORECASE,
        ):
            return RouteResult(
                intent=Intent.REJECT_ACTION,
                params={"confirmed": False},
                normalized_text=cleaned,
            )

        # 3. Compound Action Planning (e.g. "open whatsapp and send a message to lohit")
        sub_steps = self.planner.plan(cleaned)
        if len(sub_steps) > 1:
            planned_steps: list[PlannedStep] = []
            for idx, step_text in enumerate(sub_steps, start=1):
                sub_res = self._route_single_utterance(step_text, context)
                sub_params = dict(sub_res.params)
                sub_params.setdefault(
                    "desktop_action", _ACTION_MAP.get(sub_res.intent, str(sub_res.intent))
                )
                planned_steps.append(
                    PlannedStep(
                        step_index=idx,
                        intent=sub_res.intent,
                        params=sub_params,
                        description=step_text,
                    )
                )
            exec_plan = ExecutionPlan(
                original_text=cleaned,
                steps=planned_steps,
                is_compound=True,
            )
            # The primary intent is the first step's intent
            first = planned_steps[0]
            first_params = dict(first.params)
            first_params.setdefault(
                "desktop_action", _ACTION_MAP.get(first.intent, str(first.intent))
            )
            return RouteResult(
                intent=first.intent,
                params=first_params,
                confidence=0.95,
                normalized_text=cleaned,
                is_correction=norm.is_correction,
                is_compound=True,
                plan=exec_plan,
                entity=first.params.get("application")
                or first.params.get("service")
                or first.params.get("directory"),
                target=first.params.get("target"),
            )

        # 4. Route Single Utterance
        single_res = self._route_single_utterance(cleaned, context)
        single_params = dict(single_res.params)
        single_params.setdefault(
            "desktop_action", _ACTION_MAP.get(single_res.intent, str(single_res.intent))
        )
        return RouteResult(
            intent=single_res.intent,
            params=single_params,
            confidence=single_res.confidence,
            normalized_text=cleaned,
            is_correction=norm.is_correction,
            is_compound=False,
            entity=single_res.entity,
            target=single_res.target,
        )

    def _route_single_utterance(self, cleaned: str, context: Any | None = None) -> RouteResult:
        lowered = cleaned.lower()

        # ---- A. Focus / Switch App ----------------------------------------
        m_focus = re.match(
            r"^(?:focus|switch\s+to|switch\s+back\s+to|go\s+back\s+to|bring\s+up|go\s+to\s+app)\s+(?:the\s+)?(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_focus:
            cand = m_focus.group(1).strip()
            canonical = self.app_resolver.canonicalize(cand)
            if canonical:
                return RouteResult(
                    intent=Intent.FOCUS_APPLICATION,
                    params={"application": canonical},
                    entity=canonical,
                    normalized_text=cleaned,
                )

        # ---- B. Close App ------------------------------------------------
        m_close = re.match(
            r"^(?:close|kill|quit|exit|terminate)\s+(?:the\s+)?(?:app(?:lication)?\s+)?(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_close:
            cand = m_close.group(1).strip()
            if cand in {"that", "it", "this window"}:
                return RouteResult(
                    intent=Intent.CLOSE_APPLICATION,
                    params={"current": True},
                    entity="current_window",
                    normalized_text=cleaned,
                )
            canonical = self.app_resolver.canonicalize(cand)
            if canonical:
                return RouteResult(
                    intent=Intent.CLOSE_APPLICATION,
                    params={"application": canonical},
                    entity=canonical,
                    normalized_text=cleaned,
                )

        # ---- C. Navigation: Open Folder / Desktop -------------------------
        # "open desktop", "open desktop in it", "open desktop in file explorer", etc.
        m_desktop = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?desktop(?:\s+(?:in\s+it|in\s+file\s+explorer|in\s+explorer))?$",
            cleaned,
            re.IGNORECASE,
        )
        if m_desktop:
            return RouteResult(
                intent=Intent.OPEN_FOLDER,
                params={"target": "desktop", "display_name": "Desktop"},
                target="desktop",
                entity="desktop",
                normalized_text=cleaned,
            )

        m_folder = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?(downloads|documents|music|videos|pictures|project|workspace|home)(?:\s+(?:folder|directory))?(?:\s+(?:in\s+it|in\s+file\s+explorer|in\s+explorer))?$",
            cleaned,
            re.IGNORECASE,
        )
        if m_folder:
            f_name = m_folder.group(1).strip().lower()
            return RouteResult(
                intent=Intent.OPEN_FOLDER,
                params={"target": f_name, "display_name": f_name.title()},
                target=f_name,
                entity=f_name,
                normalized_text=cleaned,
            )

        # ---- D. Filesystem: List Files -----------------------------------
        if re.match(
            r"^(?:what\s+files\s+(?:are\s+)?(?:available|there|here|on\s+my\s+desktop|in\s+desktop)|(?:list|show|enumerate)\s+(?:the\s+)?files(?:\s+(?:on|in)\s+(?:the\s+|my\s+)?(?:desktop|folder|directory))?|what's\s+in\s+this\s+folder|dir|ls)$",
            cleaned,
            re.IGNORECASE,
        ):
            target_dir = "desktop" if "desktop" in lowered else None
            return RouteResult(
                intent=Intent.LIST_FILES,
                params={"directory": target_dir},
                target=target_dir or "current_directory",
                entity=target_dir or "current_directory",
                normalized_text=cleaned,
            )

        # ---- E. Filesystem: Search Files (Strictly Disambiguated) ----------
        m_search_dir = re.match(
            r"^(?:search|find|look\s+for)\s+(?:my\s+|the\s+)?(desktop|downloads|documents|workspace)\s+(?:for\s+)?(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_search_dir:
            dir_name = m_search_dir.group(1).strip().lower()
            q = m_search_dir.group(2).strip()
            return RouteResult(
                intent=Intent.SEARCH_FILES,
                params={"directory": dir_name, "query": q},
                target=dir_name,
                entity=q,
                normalized_text=cleaned,
            )

        m_search_in = re.match(
            r"^(?:search|find|look\s+for)\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+(?:my\s+|the\s+)?(desktop|downloads|documents|workspace|my\s+computer|computer|laptop|pc)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_search_in:
            q = m_search_in.group(1).strip()
            d_raw = m_search_in.group(2).strip().lower()
            dir_name = (
                "desktop"
                if "desktop" in d_raw
                else (d_raw if d_raw in {"downloads", "documents", "workspace"} else None)
            )
            return RouteResult(
                intent=Intent.SEARCH_FILES,
                params={"directory": dir_name, "query": q},
                target=dir_name or "computer",
                entity=q,
                normalized_text=cleaned,
            )

        # Search for files / shortcuts (when NOT a career query)
        file_search_pat = (
            r"^(?:search|find|look\s+for)\s+(?:for\s+)?(?:the\s+|my\s+|a\s+|an\s+)?"
            r"(resume|cv|file\s+.+|document\s+.+|latest\s+pdf|latest\s+file|latest\s+document|"
            r".+?\.(?:pdf|docx?|txt|lnk|py|json|md)|vscode|vs\s+code)$"
        )
        m_search_file = re.match(file_search_pat, cleaned, re.IGNORECASE)
        if m_search_file and not CAREER_KEYWORDS_RE.search(cleaned):
            q = m_search_file.group(1).strip()
            ext = ".pdf" if "pdf" in q.lower() else None
            p = {"query": q}
            if ext:
                p["extension"] = ext
            return RouteResult(
                intent=Intent.SEARCH_FILES,
                params=p,
                target="current_directory",
                entity=q,
                normalized_text=cleaned,
            )

        # ---- F. Open File / Contextual Ordinals / "first one" / "open it" -
        # Avoid hijacking "open file explorer"
        if re.match(r"^open\s+(?:the\s+)?file\s+explorer$", cleaned, re.IGNORECASE):
            resolved_fe = self.app_resolver.resolve("file explorer")
            if resolved_fe:
                return RouteResult(
                    intent=Intent.OPEN_APPLICATION,
                    params={
                        "application": resolved_fe.canonical_name,
                        "display_name": resolved_fe.display_name,
                        "executable": resolved_fe.executable,
                        "source": resolved_fe.source,
                    },
                    confidence=resolved_fe.confidence,
                    entity=resolved_fe.canonical_name,
                    target=resolved_fe.canonical_name,
                    normalized_text=cleaned,
                )

        # Contextual Ordinals: "first one", "the first one", "second one", "open the first one"
        m_ordinal = re.match(
            r"^(?:(?:open|view|launch|choose|select)\s+)?(?:the\s+)?(first|second|third|fourth|fifth|last|1st|2nd|3rd)(?:\s+(?:one|file|item|result))?$",
            cleaned,
            re.IGNORECASE,
        )
        if m_ordinal:
            ord_word = m_ordinal.group(1).lower()
            idx_map = {
                "first": 0,
                "1st": 0,
                "second": 1,
                "2nd": 1,
                "third": 2,
                "3rd": 2,
                "fourth": 3,
                "fifth": 4,
                "last": -1,
            }
            idx = idx_map.get(ord_word, 0)
            return RouteResult(
                intent=Intent.OPEN_FILE,
                params={"use_last_result": True, "index": idx, "ordinal": ord_word},
                target="last_search_results",
                entity=f"result_{idx}",
                normalized_text=cleaned,
            )

        # Contextual Pronoun: "open it", "open that", "open this"
        if re.match(
            r"^(?:(?:open|launch|view|choose|select)\s+)?(?:it|that|this)(?:\s+one)?$",
            cleaned,
            re.IGNORECASE,
        ):
            return RouteResult(
                intent=Intent.OPEN_FILE,
                params={"use_last_result": True, "index": 0},
                target="last_result",
                entity="last_search_result",
                normalized_text=cleaned,
            )

        m_open_resume = re.match(
            r"^(?:open|show|view)\s+(?:my\s+)?(?:resume|cv)(?:\s+(?:from|in|on)\s+(?:the\s+|my\s+)?desktop)?$",
            cleaned,
            re.IGNORECASE,
        )
        if m_open_resume:
            return RouteResult(
                intent=Intent.OPEN_FILE,
                params={"query": "resume", "target": "desktop"},
                target="desktop",
                entity="resume",
                normalized_text=cleaned,
            )

        # ---- G. Messaging / WhatsApp External Actions ---------------------
        m_msg = re.match(
            r"^(?:send\s+(?:a\s+)?message\s+to|message)\s+([a-zA-Z0-9_\s]+?)(?:\s+(?:saying|with|:)\s+(.+))?$",
            cleaned,
            re.IGNORECASE,
        )
        if not m_msg:
            m_msg = re.match(
                r"^send\s+([a-zA-Z0-9_\s]+?)\s+(?:a\s+message\s+(?:saying|with|:)\s+|['\"])(.+?)['\"]?$",
                cleaned,
                re.IGNORECASE,
            )
        if m_msg:
            recipient = m_msg.group(1).strip()
            msg_text = m_msg.group(2).strip() if m_msg.group(2) else ""
            return RouteResult(
                intent=Intent.MESSAGING_SEND,
                params={"recipient": recipient, "message": msg_text, "app": "whatsapp"},
                target=recipient,
                entity=recipient,
                normalized_text=cleaned,
            )

        # ---- H. Browser Search: Explicit Service -------------------------
        # "search for LangGraph in YouTube", "search LangGraph on YouTube"
        m_svc_search_post = re.match(
            r"^(?:search(?:\s+for)?|look\s+up)\s+(.+?)\s+(?:in|on)\s+([a-zA-Z]+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_svc_search_post:
            q_candidate = m_svc_search_post.group(1).strip()
            svc_candidate = m_svc_search_post.group(2).strip().lower()
            if svc_candidate in BROWSER_SERVICE_NAMES:
                return RouteResult(
                    intent=Intent.BROWSER_SEARCH,
                    params={"service": svc_candidate, "query": q_candidate},
                    target=svc_candidate,
                    entity=q_candidate,
                    normalized_text=cleaned,
                )

        # "search youtube for campus x", "search google for fastapi", "search on youtube for lofi"
        m_svc_search = re.match(
            r"^(?:search|look\s+up)\s+(?:on\s+|in\s+)?([a-zA-Z]+)\s+for\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_svc_search:
            svc_candidate = m_svc_search.group(1).strip().lower()
            q = m_svc_search.group(2).strip()
            if svc_candidate in BROWSER_SERVICE_NAMES:
                return RouteResult(
                    intent=Intent.BROWSER_SEARCH,
                    params={"service": svc_candidate, "query": q},
                    target=svc_candidate,
                    entity=q,
                    normalized_text=cleaned,
                )

        # "search the web for fastapi", "google fastapi"
        m_web_search = re.match(
            r"^(?:search\s+(?:the\s+web\s+for|google\s+for|online\s+for)|google\s+|look\s+up\s+)(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_web_search and not CAREER_KEYWORDS_RE.search(cleaned):
            q = m_web_search.group(1).strip()
            return RouteResult(
                intent=Intent.BROWSER_SEARCH,
                params={"service": "google", "query": q},
                target="google",
                entity=q,
                normalized_text=cleaned,
            )

        # Browser Navigation: "go back" / "back"
        if re.match(r"^(?:go\s+back|navigate\s+back|back)$", cleaned, re.IGNORECASE):
            return RouteResult(
                intent=Intent.BROWSER_BACK,
                params={},
                entity="browser",
                normalized_text=cleaned,
            )

        # ---- H. Open Application (Priority over general search / chat) ---
        m_open_app = re.match(
            r"^(?:open|launch|start|run|go\s+to|visit|navigate\s+to)\s+(?:the\s+)?(?:app(?:lication)?\s+)?(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if m_open_app:
            cand = m_open_app.group(1).strip()
            # 1. Canonical application resolution
            resolved = self.app_resolver.resolve(cand)
            if resolved:
                return RouteResult(
                    intent=Intent.OPEN_APPLICATION,
                    params={
                        "application": resolved.canonical_name,
                        "display_name": resolved.display_name,
                        "executable": resolved.executable,
                        "source": resolved.source,
                        "desktop_action": "open_app",
                    },
                    confidence=resolved.confidence,
                    entity=resolved.canonical_name,
                    target=resolved.canonical_name,
                    normalized_text=cleaned,
                )

            # 2. Direct Web Service (e.g. "open youtube", "open github")
            spec = find_service(cand.lower())
            if spec:
                is_account = spec.name == "github"
                return RouteResult(
                    intent=Intent.BROWSER_NAVIGATE,
                    params={
                        "service": spec.name,
                        "url": spec.base_url,
                        "account": is_account,
                        "desktop_action": "open_service" if is_account else "open_url",
                    },
                    target=spec.name,
                    entity=spec.name,
                    normalized_text=cleaned,
                )

            # 3. URL match
            if re.match(r"^(?:https?://)?[a-zA-Z0-9\-]+(?:\.[a-zA-Z]{2,})+(?:/\S*)?$", cand):
                url = cand if cand.startswith(("http://", "https://")) else f"https://{cand}"
                return RouteResult(
                    intent=Intent.BROWSER_NAVIGATE,
                    params={"url": url, "desktop_action": "open_url"},
                    target=url,
                    entity="url",
                    normalized_text=cleaned,
                )

        # Direct application name without "open" (e.g. "VS Code", "Chrome", "Microsoft Edge")
        resolved_direct = self.app_resolver.resolve(cleaned)
        if resolved_direct and resolved_direct.confidence >= 0.95:
            return RouteResult(
                intent=Intent.OPEN_APPLICATION,
                params={
                    "application": resolved_direct.canonical_name,
                    "display_name": resolved_direct.display_name,
                    "executable": resolved_direct.executable,
                },
                confidence=resolved_direct.confidence,
                entity=resolved_direct.canonical_name,
                normalized_text=cleaned,
            )

        # Context-dependent browser search (e.g. "Search Campus X" while in YouTube/Browser)
        m_bare_search = re.match(r"^(?:search(?:\s+for)?)\s+(.+)$", cleaned, re.IGNORECASE)
        if m_bare_search and not CAREER_KEYWORDS_RE.search(cleaned):
            q = m_bare_search.group(1).strip()
            # If context indicates browser or service, route to browser search
            browser_active = bool(context and getattr(context, "browser", None))
            return RouteResult(
                intent=Intent.BROWSER_SEARCH,
                params={"query": q, "context_aware": browser_active},
                target="browser",
                entity=q,
                normalized_text=cleaned,
            )

        # Conversational / Job details / Advice exclusions (must NOT trigger job discovery):
        if re.search(
            r"\b(?:this\s+(?:job|role|position)|why\s+(?:am|do)\s+i|about\s+(?:this|the)\s+(?:job|role)|"
            r"prepare\s+for|interview\s+tips|interview\s+prep|cover\s+letter|analy[sz]e\s+(?:my\s+)?resume)\b",
            cleaned,
            re.IGNORECASE,
        ):
            return RouteResult(
                intent=Intent.GENERAL_CONVERSATION,
                params={"text": cleaned},
                normalized_text=cleaned,
            )

        # ---- I. Career Intelligence (STRICT SIGNALS ONLY) ----------------
        has_search_verb = bool(
            re.match(
                r"^(?:find(?:\s+me)?|search(?:\s+for)?|look\s+for|hunt\s+for)\b",
                cleaned,
                re.IGNORECASE,
            )
        )
        has_career_cues = bool(CAREER_KEYWORDS_RE.search(cleaned))
        has_role_title = bool(
            re.search(
                r"\b(?:engineer|developer|designer|architect|scientist|analyst|manager|specialist|"
                r"intern|consultant|programmer|devops|fullstack|frontend|backend)\b",
                cleaned,
                re.IGNORECASE,
            )
        )
        is_legacy_test_find = cleaned.lower().strip() in {"find", "find a", "find b"}

        if (has_search_verb and (has_career_cues or has_role_title)) or is_legacy_test_find:
            return RouteResult(
                intent=Intent.CAREER_JOB_SEARCH,
                params={"query": cleaned},
                target="career_pipeline",
                entity="jobs",
                normalized_text=cleaned,
            )

        # ---- J. Fallback: General Conversation ---------------------------
        return RouteResult(
            intent=Intent.GENERAL_CONVERSATION,
            params={"text": cleaned},
            normalized_text=cleaned,
        )


# Global singleton router
default_router = IntentRouter()
