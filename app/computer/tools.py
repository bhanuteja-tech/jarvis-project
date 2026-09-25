"""Structured tool schemas and definitions for the JARVIS Autonomous Computer Agent.

Guarantees:
1. Declarative specifications with typed inputs, preconditions, risk levels,
   and verification strategies.
2. The LLM only receives these structured primitives — NO raw shell, PowerShell, or eval access.
3. High-risk operations (e.g., send_message) declare `requires_confirmation = True`.
4. Domain separation: ONLY computer-domain tools are registered here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RiskLevel = Literal["low", "medium", "high"]


@dataclass
class ComputerToolDefinition:
    """Metadata and parameter schema for an agent computer tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    required_parameters: list[str]
    risk_level: RiskLevel = "low"
    requires_confirmation: bool = False
    verification_strategy: str = "active_state"
    domain: Literal["computer"] = "computer"

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI / Ollama standard tool calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required_parameters,
                },
            },
        }


# ---------------------------------------------------------------------------
# Registry of 21+ Structured Computer Tools
# ---------------------------------------------------------------------------

COMPUTER_TOOL_DEFINITIONS: list[ComputerToolDefinition] = [
    # 1. Application Control
    ComputerToolDefinition(
        name="open_application",
        description=(
            "Launch an application by name (e.g., 'Google Chrome', 'File Explorer', 'VS Code')."
        ),
        parameters={
            "application": {
                "type": "string",
                "description": (
                    "Name of the application to open, e.g. 'Google Chrome', 'WhatsApp'."
                ),
            },
        },
        required_parameters=["application"],
        risk_level="low",
        verification_strategy="process_and_window",
    ),
    ComputerToolDefinition(
        name="focus_application",
        description="Bring an existing open application window to the foreground.",
        parameters={
            "application": {
                "type": "string",
                "description": "Name or title substring of the window to bring to the foreground.",
            },
        },
        required_parameters=["application"],
        risk_level="low",
        verification_strategy="active_window",
    ),
    ComputerToolDefinition(
        name="close_application",
        description="Close an open application gracefully.",
        parameters={
            "application": {
                "type": "string",
                "description": "Name of the application or window title to close.",
            },
        },
        required_parameters=["application"],
        risk_level="medium",
        verification_strategy="process_closed",
    ),

    # 2. Filesystem Control
    ComputerToolDefinition(
        name="open_folder",
        description=(
            "Open a folder in Windows File Explorer (e.g., 'Desktop', 'Music', 'Downloads')."
        ),
        parameters={
            "path": {
                "type": "string",
                "description": (
                    "Path or folder name like 'Desktop', 'Music', 'Downloads', or subfolder."
                ),
            },
        },
        required_parameters=["path"],
        risk_level="low",
        verification_strategy="filesystem_directory",
    ),
    ComputerToolDefinition(
        name="list_directory",
        description=(
            "List actual files and folders inside a directory. Observes real filesystem state."
        ),
        parameters={
            "directory": {
                "type": "string",
                "description": (
                    "Folder path to list. Defaults to the current active directory if omitted."
                ),
            },
            "item_type": {
                "type": "string",
                "enum": ["all", "folder", "file"],
                "description": "Filter by 'folder', 'file', or 'all'. Defaults to 'all'.",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="listing_obtained",
    ),
    ComputerToolDefinition(
        name="count_directory_items",
        description=(
            "Count how many folders or files exist inside a directory from real filesystem entries."
        ),
        parameters={
            "directory": {
                "type": "string",
                "description": (
                    "Folder to inspect. Defaults to current active directory if omitted."
                ),
            },
            "item_type": {
                "type": "string",
                "enum": ["folder", "file", "all"],
                "description": (
                    "Type of item to count: 'folder', 'file', or 'all'. Defaults to 'folder'."
                ),
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="count_calculated",
    ),
    ComputerToolDefinition(
        name="search_files",
        description="Search for files by filename pattern or query on the filesystem.",
        parameters={
            "query": {
                "type": "string",
                "description": "Filename pattern to search for, e.g. 'resume.pdf', '*.docx'.",
            },
            "directory": {
                "type": "string",
                "description": (
                    "Starting directory for the search. Defaults to home directory / Desktop."
                ),
            },
        },
        required_parameters=["query"],
        risk_level="low",
        verification_strategy="search_completed",
    ),
    ComputerToolDefinition(
        name="open_file",
        description="Open a file using its default associated Windows application.",
        parameters={
            "path": {
                "type": "string",
                "description": "Full path to the file to open.",
            },
        },
        required_parameters=["path"],
        risk_level="low",
        verification_strategy="process_and_window",
    ),

    # 3. Browser Automation
    ComputerToolDefinition(
        name="open_browser",
        description="Launch or focus the web browser.",
        parameters={
            "url": {
                "type": "string",
                "description": "Optional URL to open on launch. Defaults to homepage.",
            },
            "browser": {
                "type": "string",
                "description": "Browser name if specific (e.g. 'Google Chrome', 'Microsoft Edge').",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="process_and_window",
    ),
    ComputerToolDefinition(
        name="browser_navigate",
        description=(
            "Navigate browser to a URL (e.g. 'https://www.youtube.com/'). Reuses existing tab."
        ),
        parameters={
            "url": {
                "type": "string",
                "description": "Full URL to open.",
            },
            "browser": {
                "type": "string",
                "description": (
                    "Browser to use (e.g. 'Google Chrome'). Defaults to active browser or default."
                ),
            },
            "reuse_tab": {
                "type": "boolean",
                "description": (
                    "Whether to reuse an existing compatible tab instead of creating a new one."
                ),
            },
        },
        required_parameters=["url"],
        risk_level="low",
        verification_strategy="browser_url",
    ),
    ComputerToolDefinition(
        name="browser_search",
        description="Perform a search on a specific web platform (e.g., YouTube search).",
        parameters={
            "query": {
                "type": "string",
                "description": "The search term, e.g. 'LangGraph'.",
            },
            "site": {
                "type": "string",
                "enum": ["youtube", "google", "github"],
                "description": "Platform to search on. Defaults to 'google'.",
            },
            "browser": {
                "type": "string",
                "description": "Browser name if specific.",
            },
        },
        required_parameters=["query"],
        risk_level="low",
        verification_strategy="search_results_page",
    ),
    ComputerToolDefinition(
        name="browser_back",
        description="Navigate back in the active browser's history.",
        parameters={
            "browser": {
                "type": "string",
                "description": "Browser name if specific.",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="url_changed",
    ),
    ComputerToolDefinition(
        name="browser_forward",
        description="Navigate forward in the active browser's history.",
        parameters={
            "browser": {
                "type": "string",
                "description": "Browser name if specific.",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="url_changed",
    ),
    ComputerToolDefinition(
        name="browser_new_tab",
        description="Open a new browser tab, optionally navigating to an initial URL.",
        parameters={
            "url": {
                "type": "string",
                "description": "Optional initial URL.",
            },
            "browser": {
                "type": "string",
                "description": "Browser name if specific.",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="new_tab_active",
    ),
    ComputerToolDefinition(
        name="browser_close_tab",
        description="Close the currently active or specified browser tab.",
        parameters={
            "identifier": {
                "type": "string",
                "description": "Tab title or URL substring to close. Closes active tab if omitted.",
            },
        },
        required_parameters=[],
        risk_level="low",
        verification_strategy="tab_closed",
    ),
    ComputerToolDefinition(
        name="browser_switch_tab",
        description="Switch to an open browser tab matching an identifier or title.",
        parameters={
            "identifier": {
                "type": "string",
                "description": "Tab title, URL fragment, or ordinal index.",
            },
        },
        required_parameters=["identifier"],
        risk_level="low",
        verification_strategy="tab_active",
    ),
    ComputerToolDefinition(
        name="browser_get_state",
        description=(
            "Extract active browser state: URL, page title, and visible interactive items/videos."
        ),
        parameters={},
        required_parameters=[],
        risk_level="low",
        verification_strategy="state_captured",
    ),
    ComputerToolDefinition(
        name="browser_click",
        description=(
            "Click an element on active browser webpage by target descriptor or 1-based ordinal."
        ),
        parameters={
            "target": {
                "type": "string",
                "description": "Description, text, URL, or CSS selector of the item to click.",
            },
            "ordinal": {
                "type": "integer",
                "description": (
                    "1-based ordinal index of the item from the observed list (e.g. 3)."
                ),
            },
        },
        required_parameters=["target"],
        risk_level="low",
        verification_strategy="dom_or_url_updated",
    ),
    ComputerToolDefinition(
        name="browser_type",
        description="Type text into an input field on the active browser webpage.",
        parameters={
            "target": {
                "type": "string",
                "description": "Field description, placeholder, or selector.",
            },
            "text": {
                "type": "string",
                "description": "Text to type into the field.",
            },
        },
        required_parameters=["target", "text"],
        risk_level="low",
        verification_strategy="input_filled",
    ),

    # 4. OS & UI Interaction
    ComputerToolDefinition(
        name="ui_click",
        description="Click a native desktop UI button or element by name.",
        parameters={
            "target": {
                "type": "string",
                "description": "Name or accessible label of the UI element.",
            },
            "ordinal": {
                "type": "integer",
                "description": "1-based index if multiple matching elements exist.",
            },
        },
        required_parameters=["target"],
        risk_level="medium",
        verification_strategy="ui_state_changed",
    ),
    ComputerToolDefinition(
        name="ui_type",
        description="Type text into the currently focused desktop UI element.",
        parameters={
            "text": {
                "type": "string",
                "description": "Text string to enter.",
            },
            "target": {
                "type": "string",
                "description": "Optional name of target element.",
            },
        },
        required_parameters=["text"],
        risk_level="medium",
        verification_strategy="text_entered",
    ),
    ComputerToolDefinition(
        name="ui_press",
        description=(
            "Simulate pressing a keyboard shortcut or key (e.g. 'enter', 'tab', 'escape')."
        ),
        parameters={
            "key": {
                "type": "string",
                "description": (
                    "Key or shortcut combination to press, e.g. 'enter', 'esc', 'backspace'."
                ),
            },
        },
        required_parameters=["key"],
        risk_level="low",
        verification_strategy="key_dispatched",
    ),
    ComputerToolDefinition(
        name="get_active_window",
        description="Query the OS for the currently focused foreground window title and process.",
        parameters={},
        required_parameters=[],
        risk_level="low",
        verification_strategy="window_info",
    ),
    ComputerToolDefinition(
        name="get_computer_state",
        description=(
            "Capture authoritative computer state: active app, window, directory, browser URL."
        ),
        parameters={},
        required_parameters=[],
        risk_level="low",
        verification_strategy="state_info",
    ),

    # 5. Messaging with External Side-Effect Safety
    ComputerToolDefinition(
        name="prepare_message",
        description="Draft a message to a recipient in WhatsApp or email without sending.",
        parameters={
            "recipient": {
                "type": "string",
                "description": "Recipient contact name or phone number, e.g. 'Lohit'.",
            },
            "message": {
                "type": "string",
                "description": "Body text of the message.",
            },
            "platform": {
                "type": "string",
                "enum": ["whatsapp", "email"],
                "description": "Platform to use. Defaults to 'whatsapp'.",
            },
        },
        required_parameters=["recipient", "message"],
        risk_level="high",
        requires_confirmation=True,
        verification_strategy="message_drafted",
    ),
    ComputerToolDefinition(
        name="send_message",
        description=(
            "Send an external message to a recipient. REQUIRES CONFIRMATION before execution."
        ),
        parameters={
            "recipient": {
                "type": "string",
                "description": "Recipient contact name, e.g. 'Lohit'.",
            },
            "message": {
                "type": "string",
                "description": "Message content to transmit.",
            },
            "platform": {
                "type": "string",
                "enum": ["whatsapp", "email"],
                "description": "Platform to send through.",
            },
        },
        required_parameters=["recipient", "message"],
        risk_level="high",
        requires_confirmation=True,
        verification_strategy="message_sent",
    ),
]

COMPUTER_TOOLS_BY_NAME: dict[str, ComputerToolDefinition] = {
    t.name: t for t in COMPUTER_TOOL_DEFINITIONS
}


def get_openai_tool_schemas() -> list[dict[str, Any]]:
    """Return all computer tools formatted as OpenAI / Ollama tool schemas."""
    return [t.to_openai_schema() for t in COMPUTER_TOOL_DEFINITIONS]
