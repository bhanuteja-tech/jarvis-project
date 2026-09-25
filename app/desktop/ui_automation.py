"""Windows UI Automation Service for JARVIS.

Provides structured native accessibility element inspection, interaction,
and automation for Windows desktop applications (Buttons, TextBoxes, Lists, Trees, etc.).
Implements the tool hierarchy:
1. Native API
2. Browser DOM / Playwright
3. Windows UI Automation
4. Keyboard shortcuts
5. Mouse / coordinate automation
6. Vision-based interaction
"""

from __future__ import annotations

import logging
import platform
from typing import Any

from app.desktop.window_controller import attach_to_default_desktop

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system().lower() == "windows"

# Attempt importing uiautomation with desktop attachment already performed
UI_AUTOMATION_AVAILABLE = False
auto: Any = None

if IS_WINDOWS:
    attach_to_default_desktop()
    try:
        import uiautomation as auto  # type: ignore[import-untyped]

        UI_AUTOMATION_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("uiautomation library could not be loaded: %s", exc)
        auto = None


class UIAutomationService:
    """Provides high-level structured control inspection and manipulation."""

    def __init__(self) -> None:
        self.is_available = UI_AUTOMATION_AVAILABLE

    def _ensure_desktop(self) -> None:
        if IS_WINDOWS:
            attach_to_default_desktop()

    def find_window_control(self, hwnd: int) -> Any | None:
        """Get UI Automation WindowControl from HWND."""
        if not self.is_available or not auto:
            return None
        self._ensure_desktop()
        try:
            return auto.ControlFromHandle(hwnd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ControlFromHandle(%s) failed: %s", hwnd, exc)
            return None

    def find_element(
        self,
        root_hwnd: int | None = None,
        name: str | None = None,
        control_type: str | None = None,
        search_depth: int = 8,
    ) -> Any | None:
        """Find a structured UI element under root_hwnd (or desktop root) by name and/or type."""
        if not self.is_available or not auto:
            return None
        self._ensure_desktop()

        root = self.find_window_control(root_hwnd) if root_hwnd else auto.GetRootControl()
        if not root:
            return None

        kwargs: dict[str, Any] = {"searchDepth": search_depth}
        if name:
            kwargs["Name"] = name
        if control_type:
            kwargs["ControlTypeName"] = control_type

        try:
            ctrl = root.FindControl(
                lambda c, d: (
                    (not name or (name.lower() in (c.Name or "").lower()))
                    and (not control_type or c.ControlTypeName.lower() == control_type.lower())
                ),
                maxDepth=search_depth,
            )
            return ctrl
        except Exception as exc:  # noqa: BLE001
            logger.debug("find_element error: %s", exc)
            return None

    def find_by_name(
        self, name: str, root_hwnd: int | None = None, search_depth: int = 8
    ) -> Any | None:
        """Find element matching Name substring."""
        return self.find_element(root_hwnd=root_hwnd, name=name, search_depth=search_depth)

    def find_by_role(
        self, role_or_type: str, root_hwnd: int | None = None, search_depth: int = 8
    ) -> Any | None:
        """Find element matching ControlTypeName (e.g. ButtonControl, EditControl)."""
        return self.find_element(
            root_hwnd=root_hwnd, control_type=role_or_type, search_depth=search_depth
        )

    def click_element(self, element: Any) -> bool:
        """Click a UI element via native accessibility invocation or simulated click."""
        if not element:
            return False
        try:
            # Try InvokePattern first if supported
            if hasattr(element, "SendKeys"):
                element.Click(simulateMove=False)
                return True
            element.Click()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("click_element failed: %s", exc)
            return False

    def invoke_element(self, element: Any) -> bool:
        """Invoke element using native pattern if supported, otherwise click."""
        if not element:
            return False
        try:
            invoke_pattern = getattr(element, "GetInvokePattern", None)
            if invoke_pattern:
                pat = invoke_pattern()
                if pat:
                    pat.Invoke()
                    return True
            return self.click_element(element)
        except Exception as exc:  # noqa: BLE001
            logger.warning("invoke_element failed: %s", exc)
            return False

    def set_text(self, element: Any, text: str) -> bool:
        """Set text in an edit/textbox control using ValuePattern or SendKeys."""
        if not element:
            return False
        try:
            value_pattern = getattr(element, "GetValuePattern", None)
            if value_pattern:
                pat = value_pattern()
                if pat:
                    pat.SetValue(text)
                    return True
            if hasattr(element, "SendKeys"):
                element.SendKeys(text)
                return True
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("set_text failed: %s", exc)
            return False

    def read_text(self, element: Any) -> str:
        """Read text from an element via ValuePattern, TextPattern, or Name."""
        if not element:
            return ""
        try:
            value_pattern = getattr(element, "GetValuePattern", None)
            if value_pattern:
                pat = value_pattern()
                if pat and hasattr(pat, "Value"):
                    return str(pat.Value)
            return str(getattr(element, "Name", "") or "")
        except Exception as exc:  # noqa: BLE001
            logger.debug("read_text error: %s", exc)
            return ""

    def select_element(self, element: Any) -> bool:
        """Select a list item or selectable control."""
        if not element:
            return False
        try:
            selection_item = getattr(element, "GetSelectionItemPattern", None)
            if selection_item:
                pat = selection_item()
                if pat:
                    pat.Select()
                    return True
            return self.click_element(element)
        except Exception as exc:  # noqa: BLE001
            logger.warning("select_element failed: %s", exc)
            return False

    def inspect_window_tree(self, hwnd: int, max_depth: int = 2) -> list[dict[str, Any]]:
        """Inspect visible controls under window handle."""
        if not self.is_available or not auto:
            return []
        self._ensure_desktop()

        root = self.find_window_control(hwnd)
        if not root:
            return []

        elements: list[dict[str, Any]] = []

        def walk(ctrl: Any, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                name = ctrl.Name
                ctype = ctrl.ControlTypeName
                if name or ctype in {"ButtonControl", "EditControl", "ListControl"}:
                    elements.append(
                        {
                            "name": name,
                            "type": ctype,
                            "depth": depth,
                            "enabled": getattr(ctrl, "IsEnabled", True),
                        }
                    )
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:  # noqa: BLE001
                pass

        walk(root, 1)
        return elements


default_ui_automation = UIAutomationService()

__all__ = ["UIAutomationService", "default_ui_automation"]
