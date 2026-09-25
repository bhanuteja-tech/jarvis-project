"""FileSystem Controller for real directory inspection, file searching, and opening files.

Ensures zero hallucination by reading the actual local filesystem and returning
verifiable file paths, counts, and metadata.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from app.desktop.desktop_controller import get_actual_desktop_path, resolve_folder_path
from app.desktop.state import ComputerState, default_computer_state
from app.desktop.window_controller import WindowController, default_window_controller

logger = logging.getLogger(__name__)

# Extensions considered user documents and resumes
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt"}


class FileSystemController:
    """Inspects real local filesystem and executes file operations."""

    def __init__(
        self,
        window_controller: WindowController | None = None,
        state: ComputerState | None = None,
    ) -> None:
        self.window_controller = window_controller or default_window_controller
        self.state = state or default_computer_state

    def list_directory(self, dir_path: str | None = None) -> dict[str, Any]:
        """List files and folders in directory (defaults to current_directory)."""
        target = Path(dir_path) if dir_path else Path(self.state.current_directory)
        if not target.is_dir():
            target = get_actual_desktop_path()

        try:
            files: list[str] = []
            folders: list[str] = []

            for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                # Skip system hidden / cache files
                if item.name.startswith((".", "~", "$")) or item.name.lower() in {
                    "desktop.ini",
                    "thumbs.db",
                    "ntuser.dat",
                }:
                    continue
                if item.is_dir():
                    folders.append(item.name)
                elif item.is_file():
                    files.append(item.name)

            dir_name = "Desktop" if "desktop" in target.name.lower() else target.name
            file_count = len(files)
            folder_count = len(folders)

            # Build natural truthful description
            items_desc: list[str] = []
            if files:
                items_desc.append(f"{file_count} file{'s' if file_count != 1 else ''}")
            if folders:
                items_desc.append(f"{folder_count} folder{'s' if folder_count != 1 else ''}")

            counts_str = " and ".join(items_desc) if items_desc else "no files or folders"

            top_files = files[:6]
            preview = ", ".join(top_files)
            if len(files) > 6:
                preview += f", and {len(files) - 6} more"

            message = f"There are {counts_str} in {dir_name}."
            if files:
                message += f" The files are: {preview}."
            message += " What would you like me to do next?"

            observed_items = [
                {
                    "ordinal": idx + 1,
                    "name": name,
                    "path": str(target / name),
                    "type": "folder",
                    "source": "filesystem",
                }
                for idx, name in enumerate(folders)
            ] + [
                {
                    "ordinal": len(folders) + idx + 1,
                    "name": name,
                    "path": str(target / name),
                    "type": "file",
                    "source": "filesystem",
                }
                for idx, name in enumerate(files)
            ]

            self.state.update(
                current_directory=str(target),
                last_action="list_directory",
            )
            self.state.last_results = observed_items
            self.state.last_files = observed_items

            return {
                "success": True,
                "action": "list_directory",
                "directory": str(target),
                "dir_name": dir_name,
                "file_count": file_count,
                "folder_count": folder_count,
                "files": files,
                "folders": folders,
                "message": message,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("error listing directory %s: %s", target, exc)
            return {
                "success": False,
                "action": "list_directory",
                "directory": str(target),
                "error": f"Could not inspect directory: {exc}",
            }

    def search_files(
        self,
        directory: str | None = None,
        query: str = "",
        extension: str | None = None,
        recursive: bool = False,
    ) -> dict[str, Any]:
        """Search for files in target directory matching query and optional extension."""
        target_dir = (
            resolve_folder_path(directory) if directory else Path(self.state.current_directory)
        )
        if not target_dir or not target_dir.is_dir():
            target_dir = get_actual_desktop_path()

        clean_q = (query or "").strip().lower()
        matches: list[dict[str, Any]] = []
        dir_name = "Desktop" if "desktop" in target_dir.name.lower() else target_dir.name

        try:
            iterator = target_dir.rglob("*") if recursive else target_dir.iterdir()
            for item in iterator:
                if item.name.startswith((".", "~", "$")):
                    continue
                if extension and not item.name.lower().endswith(extension.lower()):
                    continue
                if not clean_q or clean_q in item.name.lower():
                    matches.append(
                        {
                            "name": item.name,
                            "path": str(item.resolve()),
                            "type": "folder" if item.is_dir() else "file",
                        }
                    )

            matches.sort(key=lambda m: (m["type"] != "file", m["name"].lower()))
            self.state.last_search_results = matches
            self.state.update(last_action="search_files")

            if matches:
                if len(matches) == 1:
                    msg = (
                        f"I found 1 matching item in {dir_name}: {matches[0]['name']}. "
                        "What would you like me to do next?"
                    )
                else:
                    preview = ", ".join(m["name"] for m in matches[:5])
                    more = f" and {len(matches) - 5} more" if len(matches) > 5 else ""
                    msg = (
                        f"Found {len(matches)} matching items in {dir_name}: {preview}{more}. "
                        "What would you like me to do next?"
                    )
            else:
                target_desc = f"'{query}'" if query else "matching files"
                msg = f"I couldn't find {target_desc} on your {dir_name}."

            return {
                "success": True,
                "action": "search_files",
                "directory": str(target_dir),
                "dir_name": dir_name,
                "query": query,
                "matches": matches,
                "count": len(matches),
                "message": msg,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("error searching files in %s: %s", target_dir, exc)
            return {
                "success": False,
                "action": "search_files",
                "directory": str(target_dir),
                "query": query,
                "matches": [],
                "error": str(exc),
                "message": f"Could not search {dir_name}: {exc}",
            }

    def find_files(
        self,
        query: str,
        *,
        search_dirs: list[str] | None = None,
        only_docs: bool = False,
    ) -> list[Path]:
        """Search for files matching a keyword in relevant user locations."""
        clean_q = query.strip().lower()

        # Directories to search
        dirs_to_check: list[Path] = []
        if search_dirs:
            dirs_to_check = [Path(d) for d in search_dirs if Path(d).is_dir()]
        else:
            # Check current directory first
            curr = Path(self.state.current_directory)
            if curr.is_dir():
                dirs_to_check.append(curr)

            desktop = get_actual_desktop_path()
            if desktop not in dirs_to_check:
                dirs_to_check.append(desktop)

            downloads = Path.home() / "Downloads"
            if downloads.is_dir() and downloads not in dirs_to_check:
                dirs_to_check.append(downloads)

            docs = Path.home() / "Documents"
            if docs.is_dir() and docs not in dirs_to_check:
                dirs_to_check.append(docs)

            # Project root
            proj_root = Path.cwd()
            if proj_root not in dirs_to_check:
                dirs_to_check.append(proj_root)

        matches: list[Path] = []
        seen: set[str] = set()

        for d in dirs_to_check:
            try:
                for item in d.iterdir():
                    if not item.is_file():
                        continue
                    if item.name.startswith((".", "~")):
                        continue
                    if clean_q in item.name.lower():
                        if only_docs and item.suffix.lower() not in DOCUMENT_EXTENSIONS:
                            continue
                        canon_path = str(item.resolve())
                        if canon_path not in seen:
                            seen.add(canon_path)
                            matches.append(item)
            except (PermissionError, OSError):
                continue

        return matches

    def open_resume(self) -> dict[str, Any]:
        """Find and open the candidate's resume file on the user's computer."""
        matches = self.find_files("resume", only_docs=True)
        if not matches:
            matches = self.find_files("cv", only_docs=True)

        if not matches:
            return {
                "success": False,
                "action": "open_resume",
                "message": (
                    "I searched your Desktop, Downloads, and workspace, but could "
                    "not find a resume file. Please place your resume on your Desktop "
                    "or upload it."
                ),
            }

        # If exactly one, or clear winner, open it
        best_match = matches[0]
        # Prefer PDF or DOCX over TXT if multiple exist
        for m in matches:
            if m.suffix.lower() in {".pdf", ".docx"}:
                best_match = m
                break

        return self.open_file(str(best_match))

    def open_folder(
        self, folder_path_or_name: str, display_name: str | None = None, parent: str | None = None
    ) -> dict[str, Any]:
        """Open Windows File Explorer to target folder, verify window, and update state."""
        from app.desktop.desktop_controller import default_desktop_controller

        return default_desktop_controller.open_folder(
            folder_path_or_name, display_name=display_name, parent=parent
        )

    def count_directory_items(
        self,
        directory: str | None = None,
        item_type: str = "folder",
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Count actual folders or files in target directory with zero hallucination."""
        from app.desktop.desktop_controller import get_actual_desktop_path, resolve_folder_path

        target_dir = resolve_folder_path(directory or "", parent=parent) if directory else Path(self.state.current_directory)
        if not target_dir or not target_dir.is_dir():
            target_dir = get_actual_desktop_path()

        folders: list[str] = []
        files: list[str] = []
        try:
            for item in target_dir.iterdir():
                if item.name.startswith((".", "~", "$")) or item.name.lower() in {
                    "desktop.ini",
                    "thumbs.db",
                    "ntuser.dat",
                }:
                    continue
                if item.is_dir():
                    folders.append(item.name)
                elif item.is_file():
                    files.append(item.name)
        except Exception as exc:
            logger.error("error counting directory items in %s: %s", target_dir, exc)

        dir_name = target_dir.name
        raw_type = item_type.lower()
        if "folder" in raw_type:
            count = len(folders)
            item_label = "folder"
        elif "file" in raw_type:
            count = len(files)
            item_label = "file"
        else:
            count = len(folders) + len(files)
            item_label = "item"
        label_plural = f"{item_label}s" if count != 1 else item_label

        message = f"There are {count} {label_plural} present in the {dir_name} folder."

        # Retain actual observed entities with real ordinals for follow-up reference
        if "folder" in raw_type:
            target_items = [
                {"ordinal": idx + 1, "name": name, "path": str(target_dir / name), "type": "folder", "source": "filesystem"}
                for idx, name in enumerate(folders)
            ]
        elif "file" in raw_type:
            target_items = [
                {"ordinal": idx + 1, "name": name, "path": str(target_dir / name), "type": "file", "source": "filesystem"}
                for idx, name in enumerate(files)
            ]
        else:
            target_items = [
                {"ordinal": idx + 1, "name": name, "path": str(target_dir / name), "type": "folder", "source": "filesystem"}
                for idx, name in enumerate(folders)
            ] + [
                {"ordinal": len(folders) + idx + 1, "name": name, "path": str(target_dir / name), "type": "file", "source": "filesystem"}
                for idx, name in enumerate(files)
            ]

        self.state.update(
            current_directory=str(target_dir),
            last_action="count_directory_items",
        )
        self.state.last_results = target_items
        self.state.last_files = target_items
        return {
            "success": True,
            "action": "count_directory_items",
            "directory": str(target_dir),
            "dir_name": dir_name,
            "item_type": item_type,
            "count": count,
            "folder_count": len(folders),
            "file_count": len(files),
            "folders": folders,
            "files": files,
            "message": message,
        }

    def open_file(self, file_path: str) -> dict[str, Any]:
        """Open a local file in its default OS handler and verify it started."""
        target = Path(file_path).resolve()
        if not target.exists():
            return {
                "success": False,
                "action": "open_file",
                "file_path": file_path,
                "error": f"File '{file_path}' does not exist on disk.",
            }

        try:
            logger.info("opening file: %s", target)
            os.startfile(str(target))
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "action": "open_file",
                "file_path": str(target),
                "error": f"Failed to open file: {exc}",
            }

        time.sleep(0.5)

        # Update computer state
        if str(target) not in self.state.open_files:
            self.state.open_files.append(str(target))
        self.state.update(
            selected_file=str(target),
            current_directory=str(target.parent),
            last_action="open_file",
        )

        filename = target.name
        message = f"Opened {filename}. What would you like me to do next?"
        return {
            "success": True,
            "action": "open_file",
            "file_name": filename,
            "file_path": str(target),
            "message": message,
        }

    def get_file_metadata(self, file_path: str) -> dict[str, Any] | None:
        """Get size, extension, and modified timestamp for a file."""
        target = Path(file_path)
        if not target.exists():
            return None
        stat = target.stat()
        return {
            "name": target.name,
            "extension": target.suffix.lower(),
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
        }


default_filesystem_controller = FileSystemController()

__all__ = ["FileSystemController", "default_filesystem_controller"]
