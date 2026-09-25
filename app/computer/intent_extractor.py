"""Semantic Computer Intent Extractor for JARVIS.

Converts natural-language speech/text into a structured ComputerIntent schema.

Architecture:
- Fast path: deterministic regex routing via IntentRouter (no latency).
- Slow path: LLM-structured JSON extraction for complex/compound requests.
- The LLM path is only activated when:
  (a) The deterministic router returns ``from_free_text=True`` (ambiguous), AND
  (b) The text contains indicators of complexity (multiple steps, entity
      references, compound conjunctions, browser specificity).
- When LLM is disabled/unavailable: graceful deterministic fallback.

Produces ComputerIntent objects that SemanticTaskPlanner converts to executable steps.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ApplicationTarget:
    """A specific application the user wants to open/focus/close."""
    name: str               # spoken name: "Chrome", "VS Code", "Edge"
    canonical: str          # resolved canonical key: "google_chrome"
    is_browser: bool = False
    action: str = "open"    # "open", "close", "focus"


@dataclass
class DestinationTarget:
    """A web service, URL, or channel the user wants to navigate to."""
    raw: str                # e.g. "YouTube", "CampusX", "github.com"
    url: str | None = None  # resolved URL if deterministic
    site: str | None = None # canonical site: "youtube", "github"
    is_search: bool = False
    search_query: str | None = None


@dataclass
class EntityTarget:
    """A content entity: video, course, playlist, file, contact."""
    kind: str               # "video", "course", "file", "contact", "result"
    name: str | None = None # explicit name if given
    ordinal: int | None = None  # 0-based: "third" → 2
    reference: str | None = None  # pronoun: "it", "that", "the first one"


@dataclass
class ComputerIntent:
    """Structured intent extracted from a computer-control utterance.

    Produced by ComputerIntentExtractor.  Consumed by SemanticTaskPlanner.
    """

    domain: Literal["computer"] = "computer"

    # Primary intent type (maps to Intent enum values)
    intent_type: str = "UNKNOWN"

    # Extracted targets
    application: ApplicationTarget | None = None
    destination: DestinationTarget | None = None
    entity: EntityTarget | None = None

    # Semantic specification fields
    site: str | None = None
    target_type: str | None = None
    target: str | None = None
    parent: str | None = None
    query: str | None = None
    count_only: bool = False
    clarification_prompt: str | None = None

    # Raw ordered action list for multi-step decomposition
    # E.g. ["open_browser:edge", "navigate:youtube", "search:LangGraph"]
    actions: list[str] = field(default_factory=list)

    # Contextual reference (pronoun/ordinal) if resolution is needed
    reference: EntityTarget | None = None

    # Disambiguation info
    search_domain: str | None = None   # explicit search engine/service
    explicit_browser: str | None = None  # browser name if explicitly stated

    # Source info
    raw_text: str = ""
    confidence: float = 1.0
    extraction_method: str = "deterministic"  # "deterministic" | "llm"

    @property
    def intent(self) -> str:
        return self.intent_type

    def is_multi_step(self) -> bool:
        return len(self.actions) > 1

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "domain": self.domain,
            "intent": self.intent_type,
            "intent_type": self.intent_type,
            "application": vars(self.application) if self.application else None,
            "destination": vars(self.destination) if self.destination else None,
            "entity": vars(self.entity) if self.entity else None,
            "actions": self.actions,
            "explicit_browser": self.explicit_browser,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
        }
        if self.site:
            d["site"] = self.site
        if self.target_type:
            d["target_type"] = self.target_type
        if self.target:
            d["target"] = self.target
        if self.parent:
            d["parent"] = self.parent
        if self.query:
            d["query"] = self.query
        if self.count_only:
            d["count_only"] = self.count_only
        if self.clarification_prompt:
            d["clarification_prompt"] = self.clarification_prompt
        if self.reference:
            d["reference"] = vars(self.reference) if hasattr(self.reference, "__dict__") else self.reference
        return d


# ---------------------------------------------------------------------------
# Browser alias map
# ---------------------------------------------------------------------------
_BROWSER_ALIASES: dict[str, str] = {
    "chrome": "google_chrome",
    "google chrome": "google_chrome",
    "edge": "microsoft_edge",
    "microsoft edge": "microsoft_edge",
    "msedge": "microsoft_edge",
    "firefox": "firefox",
    "mozilla": "firefox",
    "brave": "brave",
    "opera": "opera",
}

_BROWSER_RE = re.compile(
    r"\b(google\s+chrome|microsoft\s+edge|chrome|edge|firefox|mozilla\s+firefox|brave|opera)\b",
    re.IGNORECASE,
)

_ORDINAL_MAP: dict[str, int] = {
    "first": 0, "1st": 0, "one": 0,
    "second": 1, "2nd": 1, "two": 1,
    "third": 2, "3rd": 2, "three": 2,
    "fourth": 3, "4th": 3, "four": 3,
    "fifth": 4, "5th": 4, "five": 4,
    "sixth": 5, "6th": 5,
    "seventh": 6, "7th": 6,
    "eighth": 7, "8th": 7,
    "ninth": 8, "9th": 8,
    "tenth": 9, "10th": 9,
}

_ORDINAL_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\b",
    re.IGNORECASE,
)

_PRONOUN_RE = re.compile(
    r"\b(it|that|this|the\s+(?:file|video|result|course|channel|page|tab))\b",
    re.IGNORECASE,
)

# Complexity indicators that trigger LLM path
_COMPLEXITY_INDICATORS = re.compile(
    r"\b(and\s+(?:then|after|go|open|search|play|watch|navigate)|"
    r"after\s+(?:that|opening|launching)|"
    r"then\s+(?:go|open|search|navigate|play)|"
    r"(?:and|,)\s+(?:search|look\s+up|find|open|navigate))\b",
    re.IGNORECASE,
)

# Simple single-step patterns that should never trigger LLM
_SIMPLE_PATTERNS = re.compile(
    r"^(?:open|launch|start|close|focus|switch\s+to)\s+\w+$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LLM extraction schema prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are JARVIS computer intent extractor.
Convert the user's command into a JSON ComputerIntent object.

Output ONLY valid JSON with these fields:
{
  "intent_type": "<OPEN_APPLICATION|BROWSER_NAVIGATE|BROWSER_SEARCH|OPEN_FILE|"
                 "MESSAGING_SEND|SCREEN_READ|LIST_FILES|MULTI_STEP>",
  "explicit_browser": "<chrome|edge|firefox|brave|opera|null>",
  "application": {"name": "<app name or null>", "action": "<open|close|focus>"},
  "destination": {
    "raw": "<website/service name>",
    "site": "<youtube|github|etc or null>",
    "is_search": false,
    "search_query": "<query or null>"
  },
  "entity": {
    "kind": "<video|course|file|contact|result>",
    "name": "<name or null>",
    "ordinal": <0-based int or null>
  },
  "actions": ["<ordered action steps>"],
  "confidence": 0.95
}

Rules:
- If user says "Open Edge and search LangGraph on YouTube":
  actions=["open_browser:edge","navigate:youtube","search:LangGraph"]
  explicit_browser="edge"
- If user says "Open the third video": entity.ordinal=2 (0-based)
- If user says "it" or "that": entity.reference="it"
- Never invent capabilities. Keep actions concrete.
- Never hallucinate URLs.
"""


# ---------------------------------------------------------------------------
# ComputerIntentExtractor
# ---------------------------------------------------------------------------

class ComputerIntentExtractor:
    """Extracts structured ComputerIntent from natural-language computer-control utterances.

    Priority:
    1. Simple deterministic patterns (no latency, always first)
    2. LLM structured extraction (only for complex/ambiguous)
    3. Fallback: minimal intent with raw text preserved
    """

    def __init__(self, llm_client: Any | None = None) -> None:
        """
        Args:
            llm_client: Optional LLM client implementing the AssistantLlmClient
                        protocol with a ``complete_json(prompt)`` or
                        ``complete(messages)`` method.  If None, always uses
                        deterministic path.
        """
        self._llm = llm_client

    # ------------------------------------------------------------------
    def extract(self, text: str, computer_state: Any | None = None) -> ComputerIntent:
        """Extract ComputerIntent from utterance text.

        Args:
            text: Cleaned, normalized user utterance.
            computer_state: Current ComputerState for context-aware extraction.

        Returns:
            ComputerIntent with best available extraction method.
        """
        clean = text.strip()
        if not clean:
            return ComputerIntent(raw_text=text, confidence=0.0, intent_type="UNKNOWN")

        # 1. Always try deterministic first
        intent = self._extract_deterministic(clean, computer_state)

        # 2. If deterministic succeeded confidently, return it
        if intent.confidence >= 0.80:
            return intent

        # 3. Try LLM for complex cases
        if self._should_use_llm(clean) and self._llm is not None:
            llm_intent = self._extract_llm(clean, computer_state)
            if llm_intent is not None and llm_intent.confidence >= 0.70:
                return llm_intent

        # 4. Return best deterministic result
        return intent

    # ------------------------------------------------------------------
    def _should_use_llm(self, text: str) -> bool:
        """Return True if the text is complex enough to justify LLM extraction."""
        if _SIMPLE_PATTERNS.match(text):
            return False
        return bool(_COMPLEXITY_INDICATORS.search(text))

    # ------------------------------------------------------------------
    def _extract_deterministic(
        self,
        text: str,
        computer_state: Any | None = None,
    ) -> ComputerIntent:
        """Deterministic extraction for common patterns."""
        # --- Check for multi-clause compound command: "Open X and search Y on Z", etc. ---
        action_verbs = (
            r"(?:open|launch|start|run|focus|go\s+to|visit|navigate|search|"
            r"google|look\s+up|send|message|close|show|play|watch)"
        )
        compound_match = re.search(
            r"\b(?:and\s+then|then|,?\s+and)\s+" + action_verbs + r"\b",
            text,
            re.IGNORECASE,
        )
        if compound_match:
            split_pos = compound_match.start()
            clause0 = text[:split_pos].strip().rstrip(",")
            clause1_raw = text[split_pos:].strip()
            clause1 = re.sub(
                r"^(?:and\s+then|then|and|,)\s*", "", clause1_raw, flags=re.IGNORECASE
            ).strip()

            has_in_it = bool(
                re.search(r"\b(?:in\s+it|in\s+that|in\s+there)\b", clause1, re.IGNORECASE)
            )
            clean_clause1 = re.sub(
                r"\b(?:in\s+it|in\s+that|in\s+there)\b", "", clause1, flags=re.IGNORECASE
            ).strip()

            intent0 = self._extract_single_deterministic(clause0, computer_state)
            intent1 = self._extract_single_deterministic(clean_clause1, computer_state)

            if intent0.intent_type != "UNKNOWN" and intent1.intent_type != "UNKNOWN":
                combined_actions = []
                combined_actions.extend(intent0.actions)

                # If intent1 is search on a service (e.g. YouTube) and intent0 opened a browser:
                is_svc_search = (
                    intent1.destination
                    and intent1.destination.site
                    and intent1.destination.is_search
                )
                if is_svc_search:
                    svc = intent1.destination.site
                    if not any(f"navigate:{svc}" in a for a in combined_actions):
                        combined_actions.append(f"navigate:{svc}")

                # If clause1 had "open Desktop in it", and clause0 was File Explorer:
                has_open_folder = any("open_folder" in a for a in intent1.actions)
                if has_in_it and not has_open_folder and "desktop" in clean_clause1.lower():
                    combined_actions.append("open_folder:Desktop")
                combined_actions.extend(intent1.actions)

                # Deduplicate consecutive identical actions
                deduped = []
                for act in combined_actions:
                    if not deduped or deduped[-1] != act:
                        deduped.append(act)
                combined_actions = deduped

                explicit_b = intent0.explicit_browser or intent1.explicit_browser
                return ComputerIntent(
                    intent_type="MULTI_STEP",
                    application=intent0.application or intent1.application,
                    destination=intent1.destination or intent0.destination,
                    entity=intent1.entity or intent0.entity,
                    explicit_browser=explicit_b,
                    actions=combined_actions,
                    raw_text=text,
                    confidence=0.95,
                    extraction_method="deterministic_compound",
                )

        return self._extract_single_deterministic(text, computer_state)

    def _extract_single_deterministic(
        self,
        text: str,
        computer_state: Any | None = None,
    ) -> ComputerIntent:
        """Deterministic extraction for a single command clause."""
        lower = text.lower()

        # Detect explicit browser mention
        browser_match = _BROWSER_RE.search(text)
        explicit_browser: str | None = None
        if browser_match:
            bname = browser_match.group(0).lower()
            explicit_browser = next(
                (v for k, v in _BROWSER_ALIASES.items() if k in bname), None
            )

        # Detect ordinal reference
        ordinal: int | None = None
        ord_match = _ORDINAL_RE.search(lower)
        if ord_match:
            ordinal = _ORDINAL_MAP.get(ord_match.group(0).lower())

        # --- Pattern: close application ---
        m_close = re.match(r"^(?:close|quit|exit|kill|stop)\s+(.+?)$", lower)
        if m_close:
            app_name = m_close.group(1).strip()
            return ComputerIntent(
                intent_type="CLOSE_APPLICATION",
                application=ApplicationTarget(
                    name=app_name,
                    canonical=_resolve_app_canonical(app_name),
                    action="close",
                ),
                explicit_browser=explicit_browser,
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: screenshot ---
        screenshot_pat = r"\b(?:screenshot|screen\s*shot|screen\s*capture|take\s+a\s+screenshot)\b"
        if re.search(screenshot_pat, lower):
            return ComputerIntent(
                intent_type="SCREEN_READ",
                raw_text=text,
                confidence=0.98,
                extraction_method="deterministic",
            )

        # --- Pattern: search on web / service ---
        # "search YouTube for LangGraph", "search for X on GitHub", "search for React tutorials"
        m_search = re.match(
            r"^(?:search(?:\s+(?:for|the\s+web\s+for))?|google|look\s+up)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if m_search:
            raw_query = m_search.group(1).strip()

            # Check if this search is targeting the filesystem (e.g. "search for music folder")
            fs_tokens = ("folder", "directory", "file", "files", "document", "resume", "cv")
            is_explicit_web = any(k in text.lower() for k in ("web", "google", "youtube", "yt", "github", "bing", "reddit"))
            if any(tok in raw_query.lower() for tok in fs_tokens) and not is_explicit_web:
                clean_target = re.sub(r"\b(?:folder|directory|files?|documents?)\b", "", raw_query, flags=re.IGNORECASE).strip()
                return ComputerIntent(
                    domain="computer",
                    intent_type="SEARCH_FILES",
                    target_type="FOLDER" if "folder" in raw_query.lower() else "FILE",
                    target=clean_target or raw_query,
                    query=raw_query,
                    entity=EntityTarget(kind="folder" if "folder" in raw_query.lower() else "file", name=clean_target or raw_query),
                    actions=[f"search_files:{raw_query}"],
                    raw_text=text,
                    confidence=0.96,
                    extraction_method="deterministic_fs_search",
                )

            # Check if query is formatted as "on/in <service> for <q>"
            m_svc_first = re.match(
                r"^(?:on\s+|in\s+)?(youtube|yt|github|google|reddit|bing|duckduckgo|wikipedia)\s+for\s+(.+)$",
                raw_query,
                re.IGNORECASE,
            )
            # Check if query is formatted as "<q> on/in <service>"
            m_svc_last = re.match(
                r"^(.+?)\s+(?:on|in)\s+(youtube|yt|github|google|reddit|bing|duckduckgo|wikipedia)$",
                raw_query,
                re.IGNORECASE,
            )
            # Check if query is just the service itself: "search YouTube", "search on YouTube"
            m_svc_only = re.match(
                r"^(?:on\s+|in\s+)?(youtube|yt|github|google|reddit|bing|duckduckgo|wikipedia)\s*$",
                raw_query,
                re.IGNORECASE,
            )
            # Check if query is formatted as "<service> <query>": "search YouTube LangGraph"
            m_svc_prefix = re.match(
                r"^(youtube|yt|github|google|reddit|bing|duckduckgo|wikipedia)\s+(.+)$",
                raw_query,
                re.IGNORECASE,
            )
            if m_svc_first:
                svc = m_svc_first.group(1).lower()
                query = m_svc_first.group(2).strip()
            elif m_svc_last:
                svc = m_svc_last.group(2).lower()
                query = m_svc_last.group(1).strip()
            elif m_svc_only:
                svc = m_svc_only.group(1).lower()
                query = ""
            elif m_svc_prefix:
                svc = m_svc_prefix.group(1).lower()
                query = m_svc_prefix.group(2).strip()
            else:
                svc = "google"
                query = raw_query

            if svc == "yt":
                svc = "youtube"

            act = f"search:{svc}:{query}" if query else f"navigate:{svc}"
            return ComputerIntent(
                intent_type="BROWSER_SEARCH" if query else "BROWSER_NAVIGATE",
                destination=DestinationTarget(
                    raw=svc, site=svc, is_search=bool(query), search_query=query or None
                ),
                search_domain=svc,
                explicit_browser=explicit_browser,
                actions=[act],
                raw_text=text,
                confidence=0.96,
                extraction_method="deterministic",
            )

        # --- Pattern: "play/watch X on YouTube" ---
        m_play = re.match(
            r"^(?:play|watch)\s+(.+?)\s+(?:on|in)\s+(youtube|yt)\s*$", lower
        )
        if m_play:
            query = m_play.group(1).strip()
            return ComputerIntent(
                intent_type="BROWSER_SEARCH",
                destination=DestinationTarget(
                    raw="youtube", site="youtube", is_search=True, search_query=query
                ),
                search_domain="youtube",
                explicit_browser=explicit_browser,
                actions=["navigate:youtube", f"search:youtube:{query}"],
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: open specific URL ---
        m_url = re.match(
            r"^(?:open|go\s+to|navigate\s+to|visit|browse\s+to)\s+"
            r"((?:https?://)?[a-zA-Z0-9][a-zA-Z0-9\-]*(?:\.[a-zA-Z]{2,})+(?:/\S*)?)$",
            text,
            re.IGNORECASE,
        )
        if m_url:
            url = m_url.group(1)
            return ComputerIntent(
                intent_type="BROWSER_NAVIGATE",
                destination=DestinationTarget(raw=url, url=url if "." in url else None),
                explicit_browser=explicit_browser,
                actions=[f"navigate:{url}"],
                raw_text=text,
                confidence=0.94,
                extraction_method="deterministic",
            )

        # --- Pattern: send message (WhatsApp) ---
        m_msg1 = re.match(
            r"^(?:send|message|text|whatsapp)\s+(.+?)\s+(?:saying|with|the\s+message)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        m_msg2 = re.match(
            r"^(?:send|message|text)\s+(.+?)\s+to\s+(.+?)(?:\s+(?:on|via)\s+whatsapp)?$",
            text,
            re.IGNORECASE,
        )
        if m_msg1 or m_msg2:
            if m_msg1:
                recipient = m_msg1.group(1).strip()
                msg_text = m_msg1.group(2).strip()
            else:
                msg_text = m_msg2.group(1).strip()
                recipient = m_msg2.group(2).strip()

            return ComputerIntent(
                intent_type="MESSAGING_SEND",
                entity=EntityTarget(kind="contact", name=recipient),
                destination=DestinationTarget(raw="whatsapp", site="whatsapp"),
                actions=["open_app:whatsapp", f"message:{recipient}:{msg_text}"],
                raw_text=text,
                confidence=0.92,
                extraction_method="deterministic",
            )

        wc = getattr(computer_state, "web_context", None) if computer_state else None
        is_in_youtube = bool(wc and getattr(wc, "site", None) == "youtube")
        has_web_list = bool(wc and getattr(wc, "current_list", None))
        has_fs_list = bool(
            computer_state
            and (
                getattr(computer_state, "last_search_results", None)
                or getattr(computer_state, "last_files", None)
            )
        )

        # --- Pattern: How many folders / files / items ---
        # 1. With explicit or implicit directory: "how many files are available in music", "how many files in desktop", "how many files in this folder"
        m_how_many = re.match(
            r"^(?:how\s+many\s+(folders?|files?|items?)\s+(?:are\s+present\s+in|are\s+available\s+in|available\s+in|are\s+in|are\s+there\s+in|exist\s+in|are\s+found\s+in|found\s+in|are\s+there\s+inside|inside|in)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-\s]+?)(?:\s+folder|\s+directory)?\??)$",
            lower,
        )
        if not m_how_many:
            m_how_many = re.match(
                r"^(?:count\s+(?:the\s+)?(folders?|files?|items?)\s+(?:in|inside)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-\s]+?)(?:\s+folder|\s+directory)?\??)$",
                lower,
            )
        # 2. Target-less query: "how many files are available", "how many files are there", "count the files"
        m_how_many_cur = None
        if not m_how_many:
            m_how_many_cur = re.match(
                r"^(?:how\s+many\s+(folders?|files?|items?)(?:\s+(?:are\s+there|are\s+available|available|are\s+present|present|exist))?\??)$",
                lower,
            )
            if not m_how_many_cur:
                m_how_many_cur = re.match(
                    r"^(?:count\s+(?:the\s+)?(folders?|files?|items?)\??)$",
                    lower,
                )

        if m_how_many or m_how_many_cur:
            matched_group = m_how_many if m_how_many else m_how_many_cur
            raw_kind = matched_group.group(1).lower()
            entity_kind = "folder" if "folder" in raw_kind else ("file" if "file" in raw_kind else "item")
            raw_target_str = m_how_many.group(2).strip() if m_how_many else ""

            deictic = {"this", "here", "it", "this folder", "this directory", "current", "current folder", "current directory", ""}
            if raw_target_str.lower() in deictic:
                cur_dir = (computer_state.current_directory if computer_state and getattr(computer_state, "current_directory", None) else None)
                if cur_dir:
                    raw_target = Path(cur_dir).name
                elif computer_state and getattr(computer_state, "active_window_title", "") and "music" in computer_state.active_window_title.lower():
                    raw_target = "Music"
                else:
                    raw_target = "Desktop"
            else:
                raw_target = raw_target_str.capitalize()

            return ComputerIntent(
                domain="computer",
                intent_type="LIST_FILES",
                target_type="FOLDER",
                target=raw_target,
                count_only=True,
                entity=EntityTarget(kind=entity_kind, name=raw_target),
                actions=[f"count_items:{raw_target}:{entity_kind}"],
                raw_text=text,
                confidence=0.98,
                extraction_method="deterministic_count",
            )

        # --- Pattern: Go to site homepage ---
        # "Go to the homepage in YouTube", "Go to YouTube homepage", "open YouTube homepage", "go to homepage"
        m_home1 = re.match(
            r"^(?:go\s+to|navigate\s+to|open|visit)?\s*(?:the\s+)?(?:homepage|home\s+page|home)\s+(?:in|on|of)\s+([A-Za-z0-9_\-]+)$",
            lower,
        )
        m_home2 = re.match(
            r"^(?:go\s+to|navigate\s+to|open|visit)?\s*(?:the\s+)?([A-Za-z0-9_\-]+)\s+(?:homepage|home\s+page|home)$",
            lower,
        )
        m_home3 = re.match(
            r"^(?:go\s+to|navigate\s+to|open|visit)?\s*(?:the\s+)?(?:homepage|home\s+page|home)$",
            lower,
        )
        if m_home1 or m_home2 or (m_home3 and is_in_youtube):
            site_raw = m_home1.group(1) if m_home1 else (m_home2.group(1) if m_home2 else "youtube")
            site_clean = site_raw.lower().strip()
            if site_clean in ("yt", "youtube"):
                site_name = "youtube"
                home_url = "https://www.youtube.com/"
            elif site_clean in ("github", "git"):
                site_name = "github"
                home_url = "https://github.com/"
            else:
                site_name = site_clean
                home_url = f"https://www.{site_clean}.com/"

            return ComputerIntent(
                domain="computer",
                intent_type="BROWSER_NAVIGATE",
                site=site_name,
                target_type="SITE_HOME",
                target="home",
                destination=DestinationTarget(raw=site_name, site=site_name, url=home_url),
                explicit_browser=explicit_browser,
                actions=[f"navigate:{site_name}:home"],
                raw_text=text,
                confidence=0.98,
                extraction_method="deterministic_home",
            )

        # --- Pattern: open folder with parent (e.g. "open music folder in the desktop") ---
        m_folder_parent = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-]+)\s+(?:folder|directory)\s+(?:in|on)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-]+)$",
            lower,
        )
        if m_folder_parent:
            child = m_folder_parent.group(1).strip().capitalize()
            parent = m_folder_parent.group(2).strip().capitalize()
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_FOLDER",
                target_type="FOLDER",
                target=child,
                parent=parent,
                entity=EntityTarget(kind="folder", name=child),
                actions=[f"open_folder:{parent}/{child}"],
                raw_text=text,
                confidence=0.98,
                extraction_method="deterministic_folder_parent",
            )

        # --- Pattern: "open desktop in it" ---
        m_desktop_in_it = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-]+)\s+(?:in\s+it|in\s+that|in\s+there)$",
            lower,
        )
        if m_desktop_in_it:
            f_name = m_desktop_in_it.group(1).strip().capitalize()
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_FOLDER",
                target_type="FOLDER",
                target=f_name,
                entity=EntityTarget(kind="folder", name=f_name.lower()),
                actions=[f"open_folder:{f_name}"],
                raw_text=text,
                confidence=0.98,
                extraction_method="deterministic_folder_in_it",
            )

        # --- Pattern: open music folder / specific folder ---
        m_specific_folder = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?([A-Za-z0-9_\-]+)\s+folder$",
            lower,
        )
        if m_specific_folder:
            f_name = m_specific_folder.group(1).strip().capitalize()
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_FOLDER",
                target_type="FOLDER",
                target=f_name,
                entity=EntityTarget(kind="folder", name=f_name),
                actions=[f"open_folder:{f_name}"],
                raw_text=text,
                confidence=0.97,
                extraction_method="deterministic_folder",
            )

        # --- Pattern: ordinal reference (open the Nth one/video) ---
        if ordinal is not None and re.search(r"\b(?:open|play|watch|the)\b", lower):
            is_video = "video" in lower or "clip" in lower or is_in_youtube or has_web_list
            is_file = "file" in lower or "document" in lower
            if is_video:
                entity_kind = "video"
                itype = "OPEN_REFERENCE"
            elif is_file or (has_fs_list and not is_in_youtube):
                entity_kind = "file"
                itype = "OPEN_FILE"
            else:
                entity_kind = "result"
                itype = "OPEN_REFERENCE"

            return ComputerIntent(
                domain="computer",
                intent_type=itype,
                reference=EntityTarget(kind=entity_kind, ordinal=ordinal),
                entity=EntityTarget(kind=entity_kind, ordinal=ordinal),
                explicit_browser=explicit_browser,
                actions=[f"open_reference:{entity_kind}:{ordinal}"],
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: relative ordinal ("open the next video", "next one") ---
        m_next = re.match(
            r"^(?:open|play|watch|go\s+to)?\s*(?:the\s+)?next(?:\s+(?:video|one|clip|track))?$",
            lower,
        )
        if m_next:
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_REFERENCE",
                reference=EntityTarget(kind="video", reference="next"),
                entity=EntityTarget(kind="video", reference="next"),
                explicit_browser=explicit_browser,
                raw_text=text,
                confidence=0.92,
                extraction_method="deterministic",
            )

        # --- Pattern: scroll ---
        m_scroll = re.match(r"^(?:scroll(?:\s+(down|up))?|page\s+(down|up))$", lower)
        if m_scroll:
            direction = (m_scroll.group(1) or m_scroll.group(2) or "down").lower()
            return ComputerIntent(
                domain="computer",
                intent_type="SCROLL",
                entity=EntityTarget(kind="direction", name=direction),
                actions=[f"scroll:{direction}"],
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: click ---
        m_click = re.match(r"^click\s+(.+)$", lower)
        if m_click:
            click_target = m_click.group(1).strip()
            return ComputerIntent(
                domain="computer",
                intent_type="CLICK",
                entity=EntityTarget(kind="ui_element", name=click_target),
                actions=[f"click:{click_target}"],
                raw_text=text,
                confidence=0.92,
                extraction_method="deterministic",
            )

        # --- Pattern: open course / playlist / series ---
        m_course = re.match(
            r"^(?:open|show|view|find)\s+(?:the\s+)?(.+?)\s+(?:course|playlist|series|tutorial|tutorials)$",
            text,
            re.IGNORECASE,
        )
        if m_course:
            course_name = m_course.group(1).strip()
            channel = getattr(wc, "channel", None) if is_in_youtube else None
            q_term = (f"{channel} " if channel else "") + course_name
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_COURSE",
                site="youtube",
                target=course_name,
                destination=DestinationTarget(
                    raw=course_name,
                    site="youtube",
                    url=f"https://www.youtube.com/results?search_query={quote_plus(q_term)}",
                ),
                entity=EntityTarget(kind="course", name=course_name),
                explicit_browser=explicit_browser,
                actions=[f"navigate:youtube:course:{course_name}"],
                raw_text=text,
                confidence=0.94,
                extraction_method="deterministic_youtube",
            )

        # --- Pattern: open YouTube channel when in YouTube context ---
        if is_in_youtube:
            m_yt_channel = re.match(
                r"^(?:open|go\s+to|visit)\s+(?:the\s+channel\s+)?([A-Za-z0-9_\-]+(?:\s+[A-Za-z0-9_\-]+)?)(?:\s+channel)?$",
                text,
                re.IGNORECASE,
            )
            if m_yt_channel:
                candidate = m_yt_channel.group(1).strip()
                cand_lower = candidate.lower()
                non_channel_names = ("desktop", "file explorer", "settings")
                if cand_lower not in _BROWSER_ALIASES and cand_lower not in non_channel_names:
                    return ComputerIntent(
                        domain="computer",
                        intent_type="OPEN_CHANNEL",
                        site="youtube",
                        target=candidate,
                        destination=DestinationTarget(
                            raw=candidate,
                            site="youtube",
                            url=f"https://www.youtube.com/@{candidate.replace(' ', '')}",
                        ),
                        entity=EntityTarget(kind="channel", name=candidate),
                        explicit_browser=explicit_browser,
                        actions=[f"navigate:youtube:channel:{candidate}"],
                        raw_text=text,
                        confidence=0.94,
                        extraction_method="deterministic_youtube",
                    )

        # --- Pattern: open folder / desktop ---
        m_desktop = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?desktop(?:\s+(?:in\s+it|in\s+file\s+explorer|in\s+explorer))?$",
            text,
            re.IGNORECASE,
        )
        if m_desktop:
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_FOLDER",
                target_type="FOLDER",
                target="Desktop",
                entity=EntityTarget(kind="folder", name="desktop"),
                actions=["open_folder:desktop"],
                raw_text=text,
                confidence=0.96,
                extraction_method="deterministic",
            )

        m_folder = re.match(
            r"^(?:open|show|go\s+to|navigate\s+to|view)\s+(?:the\s+|my\s+)?(downloads|documents|music|videos|pictures|project|workspace|home)(?:\s+(?:folder|directory))?(?:\s+(?:in\s+it|in\s+file\s+explorer|in\s+explorer))?$",
            text,
            re.IGNORECASE,
        )
        if m_folder:
            f_name = m_folder.group(1).strip().capitalize()
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_FOLDER",
                target_type="FOLDER",
                target=f_name,
                entity=EntityTarget(kind="folder", name=f_name.lower()),
                actions=[f"open_folder:{f_name.lower()}"],
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: pronoun reference ("open it", "go there") ---
        pronoun_nav_pat = (
            r"^(?:open|go(?:\s+to)?|navigate(?:\s+to)?|play|watch|use)\s+"
            r"(?:it|that|this|there)\s*$"
        )
        if re.match(pronoun_nav_pat, lower):
            # Resolve from state if possible
            resolved = None
            if computer_state:
                from app.computer.reference_resolver import default_resolver
                resolved = default_resolver.resolve_pronoun(text, computer_state)
            if resolved and resolved.resolved:
                return ComputerIntent(
                    domain="computer",
                    intent_type="OPEN_REFERENCE",
                    reference=EntityTarget(kind="reference", reference="it"),
                    entity=EntityTarget(kind="reference", reference="it"),
                    actions=[f"navigate:{resolved.value}"],
                    raw_text=text,
                    confidence=0.90,
                    extraction_method="deterministic_resolved_pronoun",
                )
            return ComputerIntent(
                domain="computer",
                intent_type="UNKNOWN",
                clarification_prompt="I need to know what you want me to open.",
                raw_text=text,
                confidence=0.20,
                extraction_method="ambiguous_clarification",
            )

        # --- Pattern: list / show files ---
        if re.match(
            r"^(?:what\s+files\s+(?:are\s+)?(?:available|there|here|on\s+my\s+desktop|in\s+desktop)|(?:list|show|enumerate)\s+(?:the\s+|me\s+the\s+)?files(?:\s+(?:on|in)\s+(?:the\s+|my\s+)?(?:desktop|folder|directory))?|what's\s+in\s+this\s+folder|dir|ls)$",
            text,
            re.IGNORECASE,
        ):
            target_dir = "Desktop" if "desktop" in lower else "current_directory"
            return ComputerIntent(
                domain="computer",
                intent_type="LIST_FILES",
                target_type="FOLDER",
                target=target_dir,
                entity=EntityTarget(kind="directory", name=target_dir.lower()),
                actions=[f"list_files:{target_dir.lower()}"],
                raw_text=text,
                confidence=0.95,
                extraction_method="deterministic",
            )

        # --- Pattern: open course or playlist ---
        m_course = re.match(
            r"^(?:open|show|play|view)\s+(?:the\s+)?(.+?)\s+(?:course|playlist|series)$",
            text,
            re.IGNORECASE,
        )
        if m_course:
            course_name = m_course.group(1).strip()
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_CONTENT",
                target_type="COURSE",
                target=course_name,
                entity=EntityTarget(kind="course", name=course_name),
                destination=DestinationTarget(
                    raw=course_name,
                    site="youtube",
                    url=f"https://www.youtube.com/results?search_query={quote_plus(course_name)}",
                ),
                actions=[f"open_course:{course_name}"],
                raw_text=text,
                confidence=0.94,
                extraction_method="deterministic_course",
            )

        # --- Pattern: open application or web service ---
        m_open = re.match(
            r"^(?:open|launch|start|run|go\s+to|visit|navigate\s+to)\s+"
            r"(?:the\s+|a\s+|an\s+)?(?:app(?:lication)?\s+)?(.+?)(?:\s+app(?:lication)?)?$",
            text,
            re.IGNORECASE,
        )
        if m_open:
            target = m_open.group(1).strip()
            # Strip leading article if still present
            target = re.sub(r"^(?:the|a|an)\s+", "", target, flags=re.IGNORECASE).strip()
            canonical_app = _resolve_app_canonical(target)
            known_browsers = ("google_chrome", "microsoft_edge", "firefox", "brave", "opera")
            is_browser = canonical_app in known_browsers
            is_web_svc = _is_known_web_service(target)

            if is_browser:
                browser_canonical = explicit_browser or canonical_app
                return ComputerIntent(
                    domain="computer",
                    intent_type="OPEN_APPLICATION",
                    application=ApplicationTarget(
                        name=target, canonical=browser_canonical, is_browser=True
                    ),
                    explicit_browser=browser_canonical,
                    actions=[f"open_browser:{browser_canonical}"],
                    raw_text=text,
                    confidence=0.97,
                    extraction_method="deterministic",
                )
            if is_web_svc and canonical_app not in ("whatsapp", "spotify", "discord", "slack"):
                site = target.lower().strip()
                return ComputerIntent(
                    domain="computer",
                    intent_type="BROWSER_NAVIGATE",
                    site=site,
                    destination=DestinationTarget(raw=target, site=site),
                    explicit_browser=explicit_browser,
                    actions=[f"navigate:{site}"],
                    raw_text=text,
                    confidence=0.90,
                    extraction_method="deterministic",
                )

            # Check if target is a known folder
            known_folders = {"desktop", "downloads", "documents", "music", "videos", "pictures"}
            if target.lower() in known_folders or "folder" in target.lower():
                clean_f = re.sub(r"\b(?:folder|directory)\b", "", target, flags=re.IGNORECASE).strip().capitalize()
                return ComputerIntent(
                    domain="computer",
                    intent_type="OPEN_FOLDER",
                    target_type="FOLDER",
                    target=clean_f or target.capitalize(),
                    entity=EntityTarget(kind="folder", name=clean_f or target),
                    actions=[f"open_folder:{(clean_f or target).lower()}"],
                    raw_text=text,
                    confidence=0.95,
                    extraction_method="deterministic_fs_fallback",
                )

            # Explicit documentation search request ONLY (never generic Google fallback)
            if target.lower().endswith(("docs", "documentation", "guide", "handbook", "manual")):
                return ComputerIntent(
                    domain="computer",
                    intent_type="BROWSER_SEARCH",
                    destination=DestinationTarget(
                        raw="google", site="google", is_search=True, search_query=target
                    ),
                    search_domain="google",
                    explicit_browser=explicit_browser,
                    actions=[f"search:google:{target}"],
                    raw_text=text,
                    confidence=0.92,
                    extraction_method="deterministic",
                )

            # If YouTube is active, check if target is a channel navigation
            if computer_state and getattr(computer_state, "web_context", None) and getattr(computer_state.web_context, "site", None) == "youtube":
                common_os_apps = {"notepad", "calculator", "terminal", "cmd", "powershell", "paint", "explorer", "settings"}
                if canonical_app not in common_os_apps and not is_browser:
                    return ComputerIntent(
                        domain="computer",
                        intent_type="BROWSER_NAVIGATE",
                        site="youtube",
                        target_type="CHANNEL",
                        target=target,
                        destination=DestinationTarget(raw=target, site="youtube", url=f"https://www.youtube.com/@{target}"),
                        entity=EntityTarget(kind="channel", name=target),
                        actions=[f"navigate:youtube:@{target}"],
                        raw_text=text,
                        confidence=0.92,
                        extraction_method="deterministic_youtube_channel",
                    )

            # Known application launch attempt (NEVER route to Google Search)
            return ComputerIntent(
                domain="computer",
                intent_type="OPEN_APPLICATION",
                application=ApplicationTarget(name=target, canonical=canonical_app),
                explicit_browser=explicit_browser,
                actions=[f"open_app:{canonical_app}"],
                raw_text=text,
                confidence=0.88,
                extraction_method="deterministic",
            )

        # --- Compound: browser + service (low-confidence, LLM may improve) ---
        if explicit_browser and _COMPLEXITY_INDICATORS.search(text):
            return ComputerIntent(
                intent_type="MULTI_STEP",
                explicit_browser=explicit_browser,
                raw_text=text,
                confidence=0.55,  # triggers LLM path
                extraction_method="deterministic_partial",
            )

        # --- Fallback: unknown ---
        return ComputerIntent(
            raw_text=text,
            intent_type="UNKNOWN",
            explicit_browser=explicit_browser,
            confidence=0.30,
            extraction_method="deterministic_fallback",
        )

    # ------------------------------------------------------------------
    def _extract_llm(
        self,
        text: str,
        computer_state: Any | None = None,
    ) -> ComputerIntent | None:
        """Use LLM to extract structured intent for complex utterances."""
        try:
            context_summary = ""
            if computer_state:
                ctx_parts = []
                if computer_state.browser_name:
                    ctx_parts.append(f"active_browser={computer_state.browser_name}")
                if computer_state.active_page_url:
                    ctx_parts.append(f"url={computer_state.active_page_url}")
                if computer_state.web_context and computer_state.web_context.site:
                    ctx_parts.append(f"site={computer_state.web_context.site}")
                if computer_state.web_context and computer_state.web_context.channel:
                    ctx_parts.append(f"channel={computer_state.web_context.channel}")
                if ctx_parts:
                    context_summary = f"\nContext: {', '.join(ctx_parts)}"

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract intent from: '{text}'{context_summary}",
                },
            ]

            # Try structured JSON completion
            if hasattr(self._llm, "complete_json"):
                raw_json = self._llm.complete_json(messages)
            elif hasattr(self._llm, "complete"):
                raw_text = self._llm.complete(messages)
                # Extract JSON from response
                json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if not json_match:
                    return None
                raw_json = json.loads(json_match.group(0))
            else:
                logger.warning("LLM client has no complete/complete_json method")
                return None

            return _parse_llm_intent(raw_json, text)

        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM intent extraction failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

# Known web service names (subset; full catalog is in web_services.py)
_WEB_SERVICES = frozenset({
    "youtube", "yt", "github", "linkedin", "twitter", "gmail", "google",
    "chatgpt", "reddit", "leetcode", "stackoverflow", "spotify", "netflix",
    "instagram", "facebook", "notion", "figma", "vercel", "heroku",
    "campusx", "wikipedia", "whatsapp",
})

_APP_ALIASES: dict[str, str] = {
    "browser": "google_chrome",
    "web browser": "google_chrome",
    "chrome": "google_chrome",
    "google chrome": "google_chrome",
    "edge": "microsoft_edge",
    "microsoft edge": "microsoft_edge",
    "firefox": "firefox",
    "brave": "brave",
    "opera": "opera",
    "vs code": "visual_studio_code",
    "vscode": "visual_studio_code",
    "visual studio code": "visual_studio_code",
    "visual studio": "visual_studio_code",
    "notepad": "notepad",
    "calculator": "calculator",
    "calc": "calculator",
    "file explorer": "file_explorer",
    "explorer": "file_explorer",
    "whatsapp": "whatsapp",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "zoom": "zoom",
    "teams": "microsoft_teams",
    "microsoft teams": "microsoft_teams",
    "word": "microsoft_word",
    "excel": "microsoft_excel",
    "powerpoint": "microsoft_powerpoint",
    "outlook": "microsoft_outlook",
}


def _resolve_app_canonical(name: str) -> str:
    """Resolve a spoken app name to its canonical key."""
    lower = name.lower().strip()
    # Check aliases
    for alias, canonical in _APP_ALIASES.items():
        if alias in lower:
            return canonical
    # Return normalized name
    return lower.replace(" ", "_")


def _is_known_web_service(name: str) -> bool:
    """Return True if name looks like a web service."""
    lower = name.lower().strip()
    return lower in _WEB_SERVICES or "." in lower


def _parse_llm_intent(data: dict[str, Any], raw_text: str) -> ComputerIntent:
    """Parse LLM JSON response into a ComputerIntent."""
    intent_type = str(data.get("intent_type") or "UNKNOWN").upper()
    confidence = float(data.get("confidence") or 0.75)

    # Application
    app_data = data.get("application") or {}
    application: ApplicationTarget | None = None
    if app_data and app_data.get("name"):
        app_name = str(app_data["name"])
        canonical = _resolve_app_canonical(app_name)
        known_browsers = ("google_chrome", "microsoft_edge", "firefox", "brave", "opera")
        application = ApplicationTarget(
            name=app_name,
            canonical=canonical,
            is_browser=canonical in known_browsers,
            action=str(app_data.get("action") or "open"),
        )

    # Destination
    dest_data = data.get("destination") or {}
    destination: DestinationTarget | None = None
    if dest_data and dest_data.get("raw"):
        destination = DestinationTarget(
            raw=str(dest_data["raw"]),
            url=dest_data.get("url"),
            site=dest_data.get("site"),
            is_search=bool(dest_data.get("is_search", False)),
            search_query=dest_data.get("search_query"),
        )

    # Entity
    entity_data = data.get("entity") or {}
    entity: EntityTarget | None = None
    if entity_data:
        ordinal_raw = entity_data.get("ordinal")
        entity = EntityTarget(
            kind=str(entity_data.get("kind") or "result"),
            name=entity_data.get("name"),
            ordinal=int(ordinal_raw) if ordinal_raw is not None else None,
            reference=entity_data.get("reference"),
        )

    # Browser
    explicit_browser_raw = data.get("explicit_browser")
    explicit_browser: str | None = None
    if explicit_browser_raw and str(explicit_browser_raw).lower() not in ("null", "none", ""):
        explicit_browser = _APP_ALIASES.get(
            explicit_browser_raw.lower(), explicit_browser_raw.lower()
        )

    # Actions
    actions = [str(a) for a in (data.get("actions") or [])]

    return ComputerIntent(
        domain="computer",
        intent_type=intent_type,
        application=application,
        destination=destination,
        entity=entity,
        actions=actions,
        explicit_browser=explicit_browser,
        raw_text=raw_text,
        confidence=confidence,
        extraction_method="llm",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

default_extractor = ComputerIntentExtractor()

__all__ = [
    "ComputerIntent",
    "ApplicationTarget",
    "DestinationTarget",
    "EntityTarget",
    "ComputerIntentExtractor",
    "default_extractor",
]
