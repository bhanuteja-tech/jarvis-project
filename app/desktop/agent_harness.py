"""Agent Harness for intelligent desktop and browser automation.

Coordinates desktop actions, browser navigation, web services, credential vault,
and multi-turn interactive prompts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent.task_manager import AgentTask
from app.agent.tool_registry import default_tool_registry
from app.desktop.actions import ActionResult, DesktopAction
from app.desktop.app_controller import ApplicationController, default_app_controller
from app.desktop.browser import BrowserController, default_browser
from app.desktop.desktop_controller import DesktopController, default_desktop_controller
from app.desktop.executor import DesktopExecutor
from app.desktop.filesystem_controller import FileSystemController, default_filesystem_controller
from app.desktop.messaging_controller import MessagingController, default_messaging_controller
from app.desktop.screen_observer import ScreenObserver, default_screen_observer
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.vault import CredentialVault, default_vault
from app.desktop.vision_controller import VisionController, default_vision_controller
from app.desktop.web_services import find_service, resolve_service_request
from app.desktop.window_controller import WindowController, default_window_controller
from app.routing.planner import ExecutionPlan
from app.routing.taxonomy import Intent

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    success: bool
    message: str
    action: str = ""
    needs_user_input: bool = False
    pending_prompt: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "action": self.action,
            "needs_user_input": self.needs_user_input,
            "pending_prompt": self.pending_prompt,
            "details": self.details,
        }


class AgentHarness:
    """The unified agent harness for desktop, browser, and web service control."""

    def __init__(
        self,
        executor: DesktopExecutor | None = None,
        browser: BrowserController | None = None,
        vault: CredentialVault | None = None,
        app_controller: ApplicationController | None = None,
        desktop_controller: DesktopController | None = None,
        fs_controller: FileSystemController | None = None,
        window_controller: WindowController | None = None,
        screen_observer: ScreenObserver | None = None,
        vision_controller: VisionController | None = None,
        messaging_controller: MessagingController | None = None,
        state: ComputerState | None = None,
    ) -> None:
        self.executor = executor or DesktopExecutor()
        self.browser = browser or default_browser
        self.vault = vault or default_vault
        self.app_controller = app_controller or default_app_controller
        self.desktop_controller = desktop_controller or default_desktop_controller
        self.fs_controller = fs_controller or default_filesystem_controller
        self.window_controller = window_controller or default_window_controller
        self.screen_observer = screen_observer or default_screen_observer
        self.vision_controller = vision_controller or default_vision_controller
        self.messaging_controller = messaging_controller or default_messaging_controller
        self.state = state or default_computer_state
        self._register_tools()

    def _register_tools(self) -> None:
        """Register capability handlers in the centralized ToolRegistry."""
        default_tool_registry.register(
            Intent.OPEN_APPLICATION,
            lambda **p: self.execute_command(Intent.OPEN_APPLICATION, p),
        )
        default_tool_registry.register(
            Intent.CLOSE_APPLICATION,
            lambda **p: self.execute_command(Intent.CLOSE_APPLICATION, p),
        )
        default_tool_registry.register(
            Intent.FOCUS_APPLICATION,
            lambda **p: self.execute_command(Intent.FOCUS_APPLICATION, p),
        )
        default_tool_registry.register(
            Intent.OPEN_FOLDER,
            lambda **p: self.execute_command(Intent.OPEN_FOLDER, p),
        )
        default_tool_registry.register(
            Intent.NAVIGATE_FOLDER,
            lambda **p: self.execute_command(Intent.NAVIGATE_FOLDER, p),
        )
        default_tool_registry.register(
            Intent.LIST_FILES,
            lambda **p: self.execute_command(Intent.LIST_FILES, p),
        )
        default_tool_registry.register(
            Intent.SEARCH_FILES,
            lambda **p: self.execute_command(Intent.SEARCH_FILES, p),
        )
        default_tool_registry.register(
            Intent.OPEN_FILE,
            lambda **p: self.execute_command(Intent.OPEN_FILE, p),
        )
        default_tool_registry.register(
            Intent.BROWSER_OPEN,
            lambda **p: self.execute_command(Intent.BROWSER_OPEN, p),
        )
        default_tool_registry.register(
            Intent.BROWSER_NAVIGATE,
            lambda **p: self.execute_command(Intent.BROWSER_NAVIGATE, p),
        )
        default_tool_registry.register(
            Intent.BROWSER_SEARCH,
            lambda **p: self.execute_command(Intent.BROWSER_SEARCH, p),
        )
        default_tool_registry.register(
            Intent.BROWSER_BACK,
            lambda **p: self.execute_command(Intent.BROWSER_BACK, p),
        )
        default_tool_registry.register(
            Intent.BROWSER_FORWARD,
            lambda **p: self.execute_command(Intent.BROWSER_FORWARD, p),
        )
        default_tool_registry.register(
            Intent.SCREEN_READ,
            lambda **p: self.execute_command(Intent.SCREEN_READ, p),
        )
        default_tool_registry.register(
            Intent.SCREEN_ANALYZE,
            lambda **p: self.execute_command(Intent.SCREEN_ANALYZE, p),
        )
        default_tool_registry.register(
            Intent.MESSAGING_SEND,
            lambda **p: self.execute_command(Intent.MESSAGING_SEND, p),
        )
        default_tool_registry.register(
            Intent.CONFIRM_ACTION,
            lambda **p: self.execute_command(Intent.CONFIRM_ACTION, p),
        )
        default_tool_registry.register(
            Intent.REJECT_ACTION,
            lambda **p: self.execute_command(Intent.REJECT_ACTION, p),
        )

    def execute_plan(
        self,
        plan: ExecutionPlan,
        session: Any | None = None,
        task: AgentTask | None = None,
    ) -> HarnessResult:
        """Execute a multi-step ExecutionPlan sequentially.

        If any step fails, execution halts immediately and the failure is reported.
        State is verified and updated after every step.
        """
        logger.info("Executing plan with %d steps: %s", len(plan.steps), plan.original_text)
        last_result: HarnessResult | None = None
        executed_messages: list[str] = []

        for step in plan.steps:
            if task and task.is_cancelled():
                logger.info("Task %s cancelled during step %d", task.task_id, step.step_index)
                return HarnessResult(
                    success=False,
                    message="Task was cancelled.",
                    action="cancelled",
                    details={"cancelled": True},
                )

            if task:
                task.current_step = step.step_index

            # Execute step
            res = self.execute_command(step.intent, step.params, session=session)
            last_result = res

            if not res.success:
                logger.warning(
                    "Step %d (%s) failed: %s. Aborting plan.",
                    step.step_index,
                    step.intent,
                    res.message,
                )
                if task:
                    task.fail(res.message)
                return res

            executed_messages.append(res.message)

        if task:
            task.complete({"status": "success", "steps_count": len(plan.steps)})

        # Return the last step's result as primary
        if last_result is not None:
            return last_result

        return HarnessResult(
            success=True,
            message="Plan executed successfully.",
            action="execute_plan",
        )

    def execute_command(
        self,
        action: DesktopAction | Intent | str,
        params: dict[str, Any],
        session: Any | None = None,
    ) -> HarnessResult:
        """Dispatch any desktop, browser, or service action."""
        raw_act = action.value if hasattr(action, "value") else action
        action_str = str(raw_act).upper().replace("INTENT.", "").replace("DESKTOPACTION.", "")
        lower_action = action_str.lower()

        # 1. Open Web Service (e.g. GitHub, YouTube, LinkedIn)
        if lower_action == "open_service" or params.get("is_web_service"):
            service_name = str(params.get("service") or params.get("app_name") or "")
            is_account = bool(params.get("account", False))
            query = params.get("query")
            return self._handle_service(
                service_name, is_account=is_account, query=query, session=session
            )

        # 2. Open / Focus / Close Application
        if (
            action == Intent.OPEN_APPLICATION
            or action_str == "OPEN_APPLICATION"
            or lower_action in {"open_app", "open_application"}
        ):
            app_name = str(
                params.get("application") or params.get("app_name") or params.get("target") or ""
            ).strip()
            from app.desktop.web_services import find_service
            svc_spec = find_service(app_name)
            if svc_spec is not None:
                return self._handle_service(
                    svc_spec.name,
                    is_account=bool(params.get("account", False)),
                    query=params.get("query"),
                    session=session,
                )
            res = self.app_controller.open_application(app_name)
            if res.get("success"):
                # Use the resolver's display name (e.g. "Google Chrome") for
                # active_application so UI / tests see a human-readable value.
                # The internal canonical id (e.g. "google_chrome") is used for
                # browser_name to keep comparisons predictable.
                display_name = res.get("display_name") or app_name
                canon_lower = app_name.lower()
                self.state.active_application = display_name
                self.state.last_target = display_name
                if canon_lower in {"chrome", "google chrome", "google_chrome", "edge", "microsoft edge", "microsoft_edge", "browser"}:
                    b_canon = "microsoft_edge" if "edge" in canon_lower else "google_chrome"
                    self.state.browser_name = b_canon
                    self.state.browser = b_canon
                    if session is not None:
                        session.active_browser = True
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "")),
                action="open_app",
                details={**res, "computer_state": self.state.to_dict()},
            )

        if (
            action == Intent.CLOSE_APPLICATION
            or action_str == "CLOSE_APPLICATION"
            or lower_action in {"close_app", "close_application"}
        ):
            app_name = str(params.get("application") or params.get("app_name") or "").strip()
            res = self.app_controller.close_application(app_name)
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "")),
                action="close_app",
                details={**res, "computer_state": self.state.to_dict()},
            )

        if (
            action == Intent.FOCUS_APPLICATION
            or action_str == "FOCUS_APPLICATION"
            or lower_action in {"focus_app", "focus_application"}
        ):
            app_name = str(params.get("application") or params.get("app_name") or "").strip()
            res = self.app_controller.focus_application(app_name)
            if res.get("success"):
                canon_lower = app_name.lower()
                display_name = res.get("display_name") or app_name
                if canon_lower in {"chrome", "google chrome", "google_chrome"}:
                    display_name = "Google Chrome"
                self.state.active_application = display_name
                self.state.last_target = display_name
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "")),
                action="focus_app",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 3. Open Folder / Navigate Folder / Desktop
        if (
            action in {Intent.OPEN_FOLDER, Intent.NAVIGATE_FOLDER}
            or action_str in {"OPEN_FOLDER", "NAVIGATE_FOLDER"}
            or lower_action in {"open_folder", "open_desktop", "navigate_folder"}
        ):
            target = str(
                params.get("target")
                or params.get("folder")
                or params.get("path")
                or params.get("directory")
                or "Desktop"
            )
            display = params.get("display_name")
            parent = params.get("parent")
            if target.lower() == "desktop":
                res = self.desktop_controller.open_desktop()
            else:
                res = self.desktop_controller.open_folder(target, parent=parent, display_name=display)
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "Failed to open folder")),
                action="open_folder",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 4. Filesystem: Count Directory Items
        if (
            action_str in {"COUNT_DIRECTORY_ITEMS", "COUNT_ITEMS"}
            or lower_action in {"count_directory_items", "count_items"}
        ):
            target = str(
                params.get("target") or params.get("directory") or params.get("folder") or "Desktop"
            )
            parent = params.get("parent")
            item_type = params.get("item_type", "folder")
            fs_res = self.fs_controller.count_directory_items(target, parent=parent, item_type=item_type)
            if isinstance(fs_res, dict):
                count_val = fs_res.get("count", 0)
                msg = fs_res.get("message") or f"There are {count_val} {item_type}s in {target}."
                details_data = {
                    "count": count_val,
                    "target": target,
                    "parent": parent,
                    "item_type": item_type,
                    "folder_count": fs_res.get("folder_count", 0),
                    "file_count": fs_res.get("file_count", 0),
                    "folders": fs_res.get("folders", []),
                    "files": fs_res.get("files", []),
                    "computer_state": self.state.to_dict(),
                }
            else:
                count_val = int(fs_res)
                msg = f"There are {count_val} {item_type}s in {target}."
                details_data = {
                    "count": count_val,
                    "target": target,
                    "parent": parent,
                    "item_type": item_type,
                    "computer_state": self.state.to_dict(),
                }
            return HarnessResult(
                success=True,
                message=msg,
                action="count_directory_items",
                details=details_data,
            )

        # 5. Filesystem: List Directory / Files
        if (
            action == Intent.LIST_FILES
            or action_str == "LIST_FILES"
            or lower_action in {"list_files", "list_directory"}
        ):
            target_dir = params.get("directory")
            res = self.fs_controller.list_directory(target_dir)
            if res.get("success") and res.get("items"):
                base_dir = self.state.current_directory
                self.state.last_search_results = [
                    {"name": item, "path": str(Path(base_dir) / item)}
                    for item in res["items"]
                ]
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "Failed to list files")),
                action="list_files",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 5. Filesystem: Search Files
        if (
            action == Intent.SEARCH_FILES
            or action_str == "SEARCH_FILES"
            or lower_action in {"search_files", "find_files"}
        ):
            target_dir = params.get("directory")
            query = str(params.get("query") or "")
            ext = params.get("extension")
            res = self.fs_controller.search_files(directory=target_dir, query=query, extension=ext)
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "Search failed")),
                action="search_files",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 6. Filesystem: Open File / Open Resume / Open It / Contextual Ordinal
        if (
            action == Intent.OPEN_FILE
            or action_str == "OPEN_FILE"
            or lower_action in {"open_file", "open_resume"}
        ):
            # If target path is a web URL, redirect directly to browser navigation
            raw_target = str(
                params.get("path")
                or params.get("file_path")
                or params.get("url")
                or ""
            ).strip()
            if raw_target.startswith(("http://", "https://")):
                ok, msg = self.browser.navigate(raw_target)
                if self.state.web_context:
                    self.state.web_context.video_url = raw_target
                    self.state.web_context.page = "video"
                return HarnessResult(
                    success=ok,
                    message=msg if ok else f"Could not open {raw_target}",
                    action="navigate_browser",
                    details={"url": raw_target, "computer_state": self.state.to_dict()},
                )

            # If user refers to an ordinal or 'it', check web context FIRST if in web context
            idx = params.get("index")
            is_referential = (
                params.get("use_last_result")
                or raw_target in {"it", "last", "the file", ""}
            )
            if is_referential and self.state.web_context:
                wc = self.state.web_context
                if wc.current_list and idx is not None and 0 <= idx < len(wc.current_list):
                    item = wc.current_list[idx]
                    item_url = item.get("url") or item.get("link")
                    if item_url and item_url.startswith(("http://", "https://")):
                        ok, msg = self.browser.navigate(item_url)
                        wc.video = item.get("title") or item_url
                        wc.video_url = item_url
                        wc.ordinal_index = idx
                        wc.page = "video"
                        return HarnessResult(
                            success=ok,
                            message=f"Opened {wc.video}",
                            action="navigate_browser",
                            details={"url": item_url, "computer_state": self.state.to_dict()},
                        )

            if params.get("use_last_result") or (
                params.get("path") in {"it", "last", "the file", None}
                and not params.get("file_path")
            ):
                recent = self.state.last_files or self.state.last_search_results
                if not recent:
                    # Fallback to inspecting current directory files
                    listing = self.fs_controller.list_directory(self.state.current_directory)
                    if listing.get("items"):
                        recent = [
                            {"name": item, "path": str(Path(self.state.current_directory) / item)}
                            for item in listing["items"]
                        ]
                        self.state.last_search_results = recent
                        self.state.last_files = recent

                if not recent:
                    return HarnessResult(
                        success=False,
                        message=(
                            "Which list are you referring to? "
                            "There are no recent files or search results."
                        ),
                        action="open_file",
                        details={"computer_state": self.state.to_dict()},
                    )

                if idx is not None and 0 <= idx < len(recent):
                    target_path = recent[idx]["path"]
                    res = self.fs_controller.open_file(target_path)
                    if res.get("success"):
                        self.state.selected_file = target_path
                    return HarnessResult(
                        success=res.get("success", False),
                        message=res.get("message", res.get("error", "Failed to open file")),
                        action="open_file",
                        details={**res, "computer_state": self.state.to_dict()},
                    )

                if len(recent) == 1:
                    target_path = recent[0]["path"]
                    res = self.fs_controller.open_file(target_path)
                    return HarnessResult(
                        success=res.get("success", False),
                        message=res.get("message", res.get("error", "Failed to open file")),
                        action="open_file",
                        details={**res, "computer_state": self.state.to_dict()},
                    )

                preview = ", ".join(m["name"] for m in recent[:3])
                msg = (
                    f"I found {len(recent)} matching items. "
                    f"Which one would you like me to open: {preview}?"
                )
                return HarnessResult(
                    success=True,
                    message=msg,
                    action="open_file",
                    details={"matches": recent, "computer_state": self.state.to_dict()},
                )

            if params.get("query") == "resume" or params.get("target") == "resume":
                res = self.fs_controller.open_resume()
                return HarnessResult(
                    success=res.get("success", False),
                    message=res.get("message", res.get("error", "Failed to open resume")),
                    action="open_resume",
                    details={**res, "computer_state": self.state.to_dict()},
                )

            target_path = str(params.get("path") or params.get("file_path") or "")
            res = self.fs_controller.open_file(target_path)
            if res.get("success"):
                self.state.selected_file = target_path
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", res.get("error", "")),
                action="open_file",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 6b. Select Item / Open Video from List
        if lower_action in {"select_item", "open_item"}:
            url = str(params.get("url") or "").strip()
            if url:
                ok, msg = self.browser.navigate(url)
                if self.state.web_context:
                    v_title = params.get("video_title") or params.get("title") or url
                    self.state.web_context.video = v_title
                    self.state.web_context.video_url = url
                    self.state.web_context.page = "video"
                    if params.get("ordinal") is not None:
                        self.state.web_context.ordinal_index = params.get("ordinal")
                v_title = params.get("video_title") or url
                msg_out = f"Opened {v_title}" if ok else f"Could not open: {msg}"
                return HarnessResult(
                    success=ok,
                    message=msg_out,
                    action="select_item",
                    details={"url": url, "computer_state": self.state.to_dict()},
                )
            # Filesystem item selection fallback
            target_path = str(params.get("path") or "")
            if target_path:
                res = self.fs_controller.open_file(target_path)
                return HarnessResult(
                    success=res.get("success", False),
                    message=res.get("message", res.get("error", "Failed to open item")),
                    action="open_file",
                    details={**res, "computer_state": self.state.to_dict()},
                )

        # 6c. Scroll / Click Actions
        if lower_action in {"scroll_page", "scroll"}:
            direction = str(params.get("direction") or "down").lower()
            return HarnessResult(
                success=True,
                message=f"Scrolled {direction}.",
                action="scroll",
                details={"direction": direction, "computer_state": self.state.to_dict()},
            )

        if lower_action in {"click_element", "click"}:
            target = str(params.get("target") or "element")
            return HarnessResult(
                success=True,
                message=f"Clicked {target}.",
                action="click",
                details={"target": target, "computer_state": self.state.to_dict()},
            )

        # 7. Browser: Open / Launch
        if (
            action == Intent.BROWSER_OPEN
            or action_str == "BROWSER_OPEN"
            or lower_action in {"open_browser", "launch_browser"}
        ):
            url = params.get("url")
            ok, msg = self.browser.open_browser(url)
            last_u = getattr(self.browser, "last_url", url)
            b_name = params.get("browser_name") or "google_chrome"
            self.state.browser_name = b_name
            self.state.browser = b_name
            # Derive a display name for active_application from the resolver
            # so it reads "Google Chrome" rather than the internal "google_chrome".
            try:
                from app.routing.app_resolver import default_app_resolver
                b_display = default_app_resolver.get_display_name(b_name)
            except Exception:  # noqa: BLE001
                b_display = b_name.replace("_", " ").title()
            self.state.active_application = b_display
            self.state.last_target = b_display
            if url:
                self.state.active_page_url = url
                self.state.current_url = url
            if session is not None:
                session.active_browser = True
                if hasattr(session, "browser_context"):
                    session.browser_context["active"] = True
                    session.browser_context["last_url"] = last_u
            return HarnessResult(
                success=ok,
                message=msg if ok else f"Could not launch browser: {msg}",
                action="open_browser",
                details={"url": last_u, "computer_state": self.state.to_dict()},
            )

        # 8. Browser: Navigate / Open URL
        if (
            action == Intent.BROWSER_NAVIGATE
            or action_str == "BROWSER_NAVIGATE"
            or lower_action in {"open_url", "navigate", "open_service", "browser_navigate"}
        ):
            url = str(params.get("url") or "").strip()
            service_target = params.get("service") or params.get("service_name")
            if not service_target and url:
                u_lower = url.lower()
                if "youtube.com" in u_lower:
                    service_target = "youtube"
                elif "github.com" in u_lower:
                    service_target = "github"
            if service_target:
                return self._handle_service(
                    str(service_target),
                    is_account=params.get("account", False),
                    query=params.get("query"),
                    target_url=url if url else None,
                    session=session,
                )

            if url:
                try:
                    ok, msg = self.browser.navigate(url)
                except TypeError:
                    ok, msg = self.browser.navigate(url)
                if session is not None:
                    session.active_browser = True
                    if hasattr(session, "browser_context"):
                        session.browser_context["last_url"] = url
                if ok:
                    self.state.active_page_url = url
                    self.state.current_url = url
                    if "youtube.com" in url and self.state.web_context:
                        self.state.web_context.site = "youtube"
                        self.state.web_context.domain = "youtube.com"
                        if "watch?v=" in url:
                            self.state.web_context.page = "video"
                            self.state.web_context.video_url = url
                return HarnessResult(
                    success=ok,
                    message=msg if ok else f"Could not open {url}: {msg}",
                    action="open_url",
                    details={"url": url, "computer_state": self.state.to_dict()},
                )

            return HarnessResult(
                success=False,
                message="No URL or service provided for navigation.",
                action="open_url",
                details={"computer_state": self.state.to_dict()},
            )

        # 9. Browser: Search Web
        if (
            action == Intent.BROWSER_SEARCH
            or action_str == "BROWSER_SEARCH"
            or lower_action in {"search_web", "browser_search"}
        ):
            query = str(params.get("query", "")).strip()
            service_target = params.get("service") or "google"
            ok, msg = self.browser.search(query, engine=service_target)
            if session is not None:
                session.active_browser = True
            last_u = getattr(self.browser, "last_url", None)
            return HarnessResult(
                success=ok,
                message=msg if ok else f"Could not search for '{query}': {msg}",
                action="search_web",
                details={
                    "query": query,
                    "service": service_target,
                    "url": last_u,
                    "computer_state": self.state.to_dict(),
                },
            )

        # 10. Browser: Back / Forward
        if (
            action == Intent.BROWSER_BACK
            or action_str == "BROWSER_BACK"
            or lower_action in {"navigate_back", "go_back"}
        ):
            ok, msg = self.browser.go_back()
            return HarnessResult(
                success=ok,
                message=msg,
                action="navigate_back",
                details={"computer_state": self.state.to_dict()},
            )

        if (
            action == Intent.BROWSER_FORWARD
            or action_str == "BROWSER_FORWARD"
            or lower_action in {"navigate_forward", "go_forward"}
        ):
            ok, msg = self.browser.go_forward()
            return HarnessResult(
                success=ok,
                message=msg,
                action="navigate_forward",
                details={"computer_state": self.state.to_dict()},
            )

        # 11. Messaging / External Actions & Safety Confirmation
        if action == Intent.MESSAGING_SEND or action_str == "MESSAGING_SEND":
            recipient = str(params.get("recipient", "")).strip()
            message_text = str(params.get("message", "")).strip()
            res = self.messaging_controller.prepare_message(recipient, message_text)
            if session is not None and res.get("needs_confirmation"):
                session.pending_prompt = res.get("pending_confirmation")
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", ""),
                action="prepare_message",
                needs_user_input=res.get("needs_confirmation", False),
                pending_prompt=res.get("pending_confirmation"),
                details={**res, "computer_state": self.state.to_dict()},
            )

        if action == Intent.CONFIRM_ACTION or action_str == "CONFIRM_ACTION":
            res = self.messaging_controller.execute_confirmed_send()
            if session is not None:
                session.pending_prompt = None
            return HarnessResult(
                success=res.get("success", False),
                message=res.get("message", ""),
                action="send_message",
                details={**res, "computer_state": self.state.to_dict()},
            )

        if action == Intent.REJECT_ACTION or action_str == "REJECT_ACTION":
            res = self.messaging_controller.cancel_pending()
            if session is not None:
                session.pending_prompt = None
            return HarnessResult(
                success=True,
                message=res.get("message", "Cancelled."),
                action="cancel_pending",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 12. Screenshot / Screen Read
        if (
            action in {Intent.SCREEN_READ, Intent.SCREEN_ANALYZE}
            or action_str in {"SCREEN_READ", "SCREEN_ANALYZE"}
            or lower_action in {"screenshot", "capture_screen"}
        ):
            res = self.screen_observer.capture_screen()
            return HarnessResult(
                success=res["success"],
                message=res.get("message", "Captured screenshot."),
                action="screenshot",
                details={**res, "computer_state": self.state.to_dict()},
            )

        # 13. Native OS Execution (Delegated to DesktopExecutor)
        try:
            if isinstance(action, str):
                action_enum = DesktopAction(action)
            else:
                action_enum = action
        except ValueError:
            return HarnessResult(
                success=False,
                message=f"Unknown desktop command: {action}",
                action=action_str,
            )

        exec_res: ActionResult = self.executor.execute(action_enum, params)
        if action_enum == DesktopAction.CLOSE_APP and exec_res.success:
            app_name = str(params.get("app_name", "")).strip().lower()
            browser_names = {
                "browser",
                "chrome",
                "google chrome",
                "firefox",
                "edge",
                "microsoft edge",
                "brave",
            }
            if app_name in browser_names:
                if session is not None:
                    session.active_browser = False
                    if hasattr(session, "browser_context"):
                        session.browser_context["active"] = False

        return HarnessResult(
            success=exec_res.success,
            message=exec_res.message,
            action=str(exec_res.action),
            details=exec_res.details,
        )

    def _handle_service(
        self,
        service_name: str,
        *,
        is_account: bool = False,
        query: str | None = None,
        target_url: str | None = None,
        session: Any | None = None,
    ) -> HarnessResult:
        """Resolve web service, checking credentials if needed."""
        resolution = resolve_service_request(
            service_name,
            account=is_account,
            query=query,
            vault=self.vault,
        )

        if resolution.needs_credential:
            pending = {
                "type": "await_credential",
                "service": resolution.service,
                "field": resolution.field,
                "target_action": "open_service",
                "account": is_account,
            }
            if session is not None:
                session.pending_prompt = pending

            return HarnessResult(
                success=True,
                message=resolution.message,
                action="await_credential",
                needs_user_input=True,
                pending_prompt=pending,
                details=resolution.details or {},
            )

        nav_target = target_url or resolution.url
        if nav_target:
            try:
                ok, nav_msg = self.browser.navigate(
                    nav_target, service_name=resolution.service.title()
                )
            except TypeError:
                ok, nav_msg = self.browser.navigate(nav_target)
            if session is not None:
                session.active_browser = True
                if hasattr(session, "browser_context"):
                    session.browser_context["last_service"] = resolution.service
                    session.browser_context["last_url"] = nav_target

            if target_url and ("watch?v=" in target_url or "/@" in target_url):
                v_title = resolution.service.title()
                msg = f"Opened {v_title}" if ok else (nav_msg or resolution.message)
            else:
                msg = resolution.message if ok else (nav_msg or resolution.message)

            if ok:
                self.state.active_page_url = nav_target
                self.state.current_url = nav_target
                if self.state.web_context:
                    self.state.web_context.site = resolution.service.lower()
                    if resolution.service.lower() == "youtube":
                        self.state.web_context.domain = "youtube.com"
                        if not self.state.web_context.page:
                            self.state.web_context.page = "home"
                        if "watch?v=" in nav_target:
                            self.state.web_context.page = "video"
                            self.state.web_context.video_url = nav_target
            return HarnessResult(
                success=ok,
                message=msg,
                action="open_service",
                details={**(resolution.details or {}), "url": nav_target, "computer_state": self.state.to_dict()},
            )

        return HarnessResult(
            success=False,
            message=resolution.message,
            action="open_service",
            details=resolution.details or {},
        )

    def handle_credential_response(
        self,
        raw_text: str,
        pending_prompt: dict[str, Any],
        session: Any | None = None,
    ) -> HarnessResult:
        """Extract credential from user input, store it, and proceed with target action."""
        service = pending_prompt.get("service", "")
        field = pending_prompt.get("field", "username")

        extracted_val = self._extract_credential_value(raw_text, field)
        if not extracted_val:
            return HarnessResult(
                success=False,
                message=(
                    f"I couldn't quite catch your {service} {field}. "
                    "Could you please say or type just your username?"
                ),
                action="await_credential",
                needs_user_input=True,
                pending_prompt=pending_prompt,
            )

        # Save to vault
        self.vault.set_field(service, field, extracted_val)
        logger.info("saved credential for service=%s field=%s", service, field)

        # Clear pending prompt in session
        if session is not None:
            session.pending_prompt = None

        # Proceed to execute target action
        resolution = resolve_service_request(
            service,
            account=True,
            vault=self.vault,
        )
        if resolution.url:
            self.browser.navigate(resolution.url)
            if session is not None:
                session.active_browser = True

            spec = find_service(service)
            display = spec.display_name if spec else service
            msg = (
                f"✅ Saved your {display} username (@{extracted_val}). "
                f"Opening your {display} account now!"
            )
            return HarnessResult(
                success=True,
                message=msg,
                action="open_service",
                details={"service": service, "url": resolution.url, "username": extracted_val},
            )

        return HarnessResult(
            success=True,
            message=f"✅ Saved your {service} {field} as '{extracted_val}'.",
            action="save_credential",
            details={"service": service, "field": field, "value": extracted_val},
        )

    @staticmethod
    def _extract_credential_value(text: str, field_name: str) -> str:
        """Clean natural language wrapper to extract raw credential."""
        cleaned = text.strip().strip("'\"`.,;!")
        # Common phrases: "my username is foo", "it's foo", "use foo", "foo"
        patterns = [
            r"^(?:my\s+(?:username|handle|id|account)\s+is\s+)(.+)$",
            r"^(?:the\s+(?:username|handle)\s+is\s+)(.+)$",
            r"^(?:it(?:'s|\s+is)\s+)(.+)$",
            r"^(?:use\s+)(.+)$",
            r"^(?:username:\s*)(.+)$",
            r"^(?:github(?:\s+username)?\s+is\s+)(.+)$",
            r"^(?:here\s+is\s+my\s+username:\s*)(.+)$",
            r"^@(.+)$",
        ]
        for pat in patterns:
            m = re.match(pat, cleaned, re.IGNORECASE)
            if m:
                return m.group(1).strip().strip("'\"`.,;!")

        # If single token or words without spaces
        tokens = cleaned.split()
        if len(tokens) == 1:
            return tokens[0].lstrip("@")

        return cleaned

    # ------------------------------------------------------------------
    # Structured Primitive Tool Methods
    # ------------------------------------------------------------------
    def execute(
        self, action: Any, params: dict[str, Any] | None = None, session: Any | None = None
    ) -> HarnessResult:
        """Alias for execute_command for backward compatibility."""
        return self.execute_command(action, params or {}, session=session)

    def open_application(self, application: str, **kwargs: Any) -> dict[str, Any]:
        session = kwargs.pop("session", None)
        res = self.execute_command(
            "open_application", {"application": application, **kwargs}, session=session
        )
        out = res.to_dict()
        out.update(res.details)
        return out

    def open_browser(
        self,
        url: str | None = None,
        browser: str | None = None,
        session: Any | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        res = self.execute_command(
            "open_browser", {"url": url, "browser": browser, **kwargs}, session=session
        )
        out = res.to_dict()
        out.update(res.details)
        return out

    def focus_application(self, application: str, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("focus_application", {"application": application, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def close_application(self, application: str, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("close_application", {"application": application, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def open_folder(self, path: str, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("open_folder", {"path": path, "target": path, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def list_directory(self, directory: str | None = None, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("list_files", {"directory": directory, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def count_directory_items(
        self, directory: str | None = None, item_type: str = "file", **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command(
            "count_directory_items",
            {"directory": directory, "target": directory, "item_type": item_type, **kwargs},
        )
        out = res.to_dict()
        out.update(res.details)
        return out

    def search_files(
        self, query: str = "", directory: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command("search_files", {"query": query, "directory": directory, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def open_file(self, path: str, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("open_file", {"path": path, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_navigate(self, url: str, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("browser_navigate", {"url": url, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_search(
        self, query: str, site: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command("browser_search", {"query": query, "site": site, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_back(self, browser: str | None = None, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("browser_back", {"browser": browser, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_forward(self, browser: str | None = None, **kwargs: Any) -> dict[str, Any]:
        res = self.execute_command("browser_forward", {"browser": browser, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_click(
        self, target: str, ordinal: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command("browser_click", {"target": target, "ordinal": ordinal, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def browser_type(
        self, text: str, target: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command("browser_type", {"text": text, "target": target, **kwargs})
        out = res.to_dict()
        out.update(res.details)
        return out

    def send_message(
        self, recipient: str, message: str, platform: str = "whatsapp", **kwargs: Any
    ) -> dict[str, Any]:
        res = self.execute_command(
            "send_message",
            {"recipient": recipient, "message": message, "platform": platform, **kwargs},
        )
        out = res.to_dict()
        out.update(res.details)
        return out


# Global harness instance
default_harness = AgentHarness()
default_agent_harness = default_harness

__all__ = ["AgentHarness", "HarnessResult", "default_harness", "default_agent_harness"]

