"""Semantic Firewall & Tool Validator for the JARVIS Autonomous Computer Agent.

Guarantees:
1. Strict Domain Isolation: Blocks any career intelligence tools (job_search, resume_tailor, etc.)
   from executing in the computer domain.
2. Parameter & Type Enforcement: Validates required arguments, schema conformance, and values.
3. Entity Compatibility: Ensures ordinal references match the active domain entities.
4. Confirmation Guard: Identifies destructive or external side-effect actions (like send_message)
   and forces user confirmation before dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.computer.context import TypedContext
from app.computer.tools import COMPUTER_TOOLS_BY_NAME, ComputerToolDefinition

# Forbidden tools in the Computer domain (must never escape into career pipeline)
FORBIDDEN_CAREER_TOOLS = {
    "job_search",
    "search_jobs",
    "resume_tailor",
    "tailor_resume",
    "jd_analysis",
    "analyze_jd",
    "job_matching",
    "match_jobs",
    "career_discovery",
    "build_candidate_profile",
}


@dataclass
class ToolValidationResult:
    """Outcome of evaluating a proposed tool call through the semantic firewall."""

    valid: bool
    tool_name: str
    arguments: dict[str, Any]
    definition: ComputerToolDefinition | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
            "rejection_reason": self.rejection_reason,
        }


TOOL_ALIASES: dict[str, str] = {
    "open_app": "open_application",
    "launch_app": "open_application",
    "launch_application": "open_application",
    "focus_app": "focus_application",
    "close_app": "close_application",
    "dir": "list_directory",
    "list_files": "list_directory",
    "count_files": "count_directory_items",
    "count_items": "count_directory_items",
    "find_files": "search_files",
    "search_file": "search_files",
    "navigate": "browser_navigate",
    "search": "browser_search",
    "send_msg": "send_message",
    "back": "browser_back",
    "go_back": "browser_back",
    "navigate_back": "browser_back",
    "launch_browser": "open_browser",
    "open_a_browser": "open_browser",
}

ARGUMENT_SYNONYMS: dict[str, list[str]] = {
    "application": ["app", "app_name", "name", "target", "application_name", "app_title"],
    "path": [
        "folder", "directory", "dir", "file", "filepath", "target", "folder_path", "path_name"
    ],
    "directory": ["folder", "path", "dir", "target"],
    "item_type": ["type", "kind"],
    "query": ["q", "search_query", "text", "search_term", "keyword"],
    "recipient": ["contact", "to", "user", "person", "target", "name"],
    "message": ["text", "body", "content", "msg"],
    "url": ["link", "target_url", "uri", "address"],
    "platform": ["service", "app"],
}


class SemanticFirewall:
    """Semantic security gatekeeper for agent tool calls."""

    def __init__(self, domain: str = "computer") -> None:
        self.domain = domain

    def validate_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: TypedContext,
        confirmed: bool = False,
    ) -> ToolValidationResult:
        """Validate proposed tool call against schemas, domain rules, and active context."""
        canon_tool_name = TOOL_ALIASES.get(tool_name.lower().strip(), tool_name)

        # Smart tool intent normalization
        if canon_tool_name == "browser_navigate":
            nav_target = str(
                arguments.get("url")
                or arguments.get("target")
                or arguments.get("application")
                or ""
            ).strip().lower()
            desktop_apps = (
                "chrome", "google chrome", "google_chrome", "whatsapp",
                "vs code", "vscode", "visual studio code", "file explorer"
            )
            if nav_target in desktop_apps:
                canon_tool_name = "open_application"
                app_dest = (
                    "Google Chrome"
                    if "chrome" in nav_target
                    else (
                        "Visual Studio Code"
                        if "vs" in nav_target
                        else ("WhatsApp" if "whatsapp" in nav_target else "File Explorer")
                    )
                )
                arguments = {"application": app_dest}
            elif nav_target in ("back", "previous", "go back"):
                canon_tool_name = "browser_back"
                arguments = {}
            elif arguments.get("ordinal") is not None:
                canon_tool_name = "browser_click"

        # 1. Domain Escape Check
        if canon_tool_name.lower() in FORBIDDEN_CAREER_TOOLS:
            return ToolValidationResult(
                valid=False,
                tool_name=canon_tool_name,
                arguments=arguments,
                rejection_reason=(
                    f"Cross-domain violation: '{canon_tool_name}' belongs to Career Intelligence "
                    f"and cannot be invoked from the Computer Agent."
                ),
            )

        # 2. Known Tool Check
        definition = COMPUTER_TOOLS_BY_NAME.get(canon_tool_name)
        if not definition:
            return ToolValidationResult(
                valid=False,
                tool_name=canon_tool_name,
                arguments=arguments,
                rejection_reason=f"Unknown or unsupported computer tool: '{canon_tool_name}'.",
            )

        # 3. Parameter Normalization & Validation
        cleaned_args = dict(arguments or {})
        for canonical_param in definition.parameters:
            if canonical_param not in cleaned_args or cleaned_args[canonical_param] in (None, ""):
                for syn in ARGUMENT_SYNONYMS.get(canonical_param, []):
                    if syn in cleaned_args and cleaned_args[syn] not in (None, ""):
                        cleaned_args[canonical_param] = cleaned_args[syn]
                        break

        if canon_tool_name in ("open_application", "focus_application"):
            app_raw = str(cleaned_args.get("application") or "").lower().strip()
            # If target is a standard user folder, route to open_folder
            if app_raw in ("music", "desktop", "downloads", "documents", "pictures", "videos"):
                canon_tool_name = "open_folder"
                definition = COMPUTER_TOOLS_BY_NAME.get("open_folder")
                cleaned_args = {"path": app_raw.title()}
            # If target matches an active youtube video entity, route to browser_click
            elif context.youtube_video_results and context.last_active_domain != "filesystem":
                matched_video = None
                for yv in context.youtube_video_results:
                    if (
                        yv.title.lower() == app_raw
                        or app_raw in yv.title.lower()
                        or f"#{yv.ordinal}" in app_raw
                        or f"video {yv.ordinal}" in app_raw
                        or f"{yv.ordinal}" in app_raw
                    ):
                        matched_video = yv
                        break
                if matched_video:
                    canon_tool_name = "browser_click"
                    definition = COMPUTER_TOOLS_BY_NAME.get("browser_click")
                    cleaned_args = {"target": matched_video.url, "ordinal": matched_video.ordinal}
            elif app_raw in ("chrome", "google chrome", "google_chrome"):
                cleaned_args["application"] = "Google Chrome"
            elif app_raw in ("vscode", "vs code", "visual studio code"):
                cleaned_args["application"] = "Visual Studio Code"
            elif app_raw in ("whatsapp",):
                cleaned_args["application"] = "WhatsApp"
            elif app_raw in ("file explorer", "explorer"):
                cleaned_args["application"] = "File Explorer"

        if (
            canon_tool_name in ("send_message", "prepare_message")
            and not cleaned_args.get("platform")
        ):
            cleaned_args["platform"] = "whatsapp"

        missing_params = [
            param for param in definition.required_parameters
            if param not in cleaned_args or cleaned_args[param] is None or cleaned_args[param] == ""
        ]
        if missing_params:
            return ToolValidationResult(
                valid=False,
                tool_name=canon_tool_name,
                arguments=cleaned_args,
                definition=definition,
                rejection_reason=(
                    f"Missing required parameter(s) for '{canon_tool_name}': "
                    f"{', '.join(missing_params)}."
                ),
            )

        # 4. Context & Ordinal Compatibility Check
        ordinal = cleaned_args.get("ordinal")
        if ordinal is not None and isinstance(ordinal, int):
            if ordinal < 1:
                return ToolValidationResult(
                    valid=False,
                    tool_name=canon_tool_name,
                    arguments=cleaned_args,
                    definition=definition,
                    rejection_reason=(
                        f"Invalid ordinal {ordinal}; ordinals must be 1-based positive integers."
                    ),
                )

            # Check if this tool is browser clicking vs filesystem navigation
            if canon_tool_name == "browser_click":
                # Ensure we have browser or youtube entities if targeting video
                if not context.youtube_video_results and not context.browser_search_results:
                    # In case user requested video click but active context is filesystem
                    if context.filesystem_results:
                        return ToolValidationResult(
                            valid=False,
                            tool_name=canon_tool_name,
                            arguments=cleaned_args,
                            definition=definition,
                            rejection_reason=(
                                f"Context mismatch: Requested browser click for ordinal {ordinal}, "
                                f"but current active context is filesystem "
                                f"({len(context.filesystem_results)} items)."
                            ),
                        )

        # 5. External Side Effect & Confirmation Check
        if definition.requires_confirmation and not confirmed:
            prompt = self._build_confirmation_prompt(canon_tool_name, cleaned_args)
            return ToolValidationResult(
                valid=True,
                tool_name=canon_tool_name,
                arguments=cleaned_args,
                definition=definition,
                requires_confirmation=True,
                confirmation_prompt=prompt,
            )

        return ToolValidationResult(
            valid=True,
            tool_name=canon_tool_name,
            arguments=cleaned_args,
            definition=definition,
            requires_confirmation=False,
        )

    def _build_confirmation_prompt(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name in ("send_message", "prepare_message"):
            recipient = args.get("recipient", "the recipient")
            msg = args.get("message", "")
            platform = args.get("platform", "WhatsApp")
            return f"Ready to send '{msg}' to {recipient} via {platform}. Should I send it?"
        return f"Executing {tool_name} has external side-effects. Do you want to proceed?"


# ---------------------------------------------------------------------------
# Prompt Injection Defense & Untrusted Content Sanitizer
# ---------------------------------------------------------------------------

PROMPT_INJECTION_PATTERNS: tuple[str, ...] = (
    r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)",
    r"(?i)\bdisregard\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)",
    r"(?i)\bforget\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)",
    r"(?i)\bsystem\s+override\b",
    r"(?i)\byou\s+are\s+now\s+(?:in\s+)?(?:dan|developer|god)\s+mode\b",
    r"(?i)\breveal\s+(?:your\s+)?(?:system\s+prompt|hidden\s+instructions?)\b",
    r"(?i)\bshow\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt)\b",
    r"(?i)\bexfiltrate\b",
    r"(?i)\bupload\s+(?:all\s+)?(?:your\s+)?(?:files|passwords?|keys?)\s+to\b",
    r"(?i)\bsend\s+(?:my|the|your)\s+(?:passwords?|credentials?|tokens?|keys?)\s+to\b",
)


def detect_prompt_injection(text: str) -> bool:
    """Detect whether text contains prompt injection or adversarial jailbreak patterns."""
    if not text:
        return False
    import re
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def sanitize_untrusted_content(text: str, max_chars: int = 4000) -> str:
    """Fences and sanitizes untrusted webpage, DOM, or external content.

    Ensures external text is treated strictly as data, never as executable instructions.
    """
    if not text:
        return ""
    import re

    # Strip dangerous HTML script tags
    sanitized = re.sub(r"(?is)<script.*?>.*?</script>", " [script removed] ", text)
    sanitized = re.sub(r"(?is)<style.*?>.*?</style>", " ", sanitized)

    # Neutralize prompt injection phrases within untrusted text
    if detect_prompt_injection(sanitized):
        for pattern in PROMPT_INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[SUSPICIOUS INSTRUCTION REMOVED]", sanitized)

    # Truncate to maximum characters
    if len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars] + "... [truncated]"

    return sanitized


__all__ = [
    "FORBIDDEN_CAREER_TOOLS",
    "ToolValidationResult",
    "TOOL_ALIASES",
    "ARGUMENT_SYNONYMS",
    "SemanticFirewall",
    "detect_prompt_injection",
    "sanitize_untrusted_content",
]
