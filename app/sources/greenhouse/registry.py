"""Board registry: operator-maintained `board_token -> company_name` mapping.

Decision A (approved): Greenhouse's jobs-list endpoint does not include the
company name, and we do not invent values from API responses. The company
display name therefore comes from configuration maintained by the operator.

The registry is intentionally a small Protocol plus one file-backed
implementation:

- It is configuration-backed (a JSON file), not a hardcoded Python dict.
- It can be replaced later by a database-backed implementation implementing
  `BoardRegistryProtocol` without any change to the Greenhouse adapter.

JSON file format (flat object)::

    {"very_awesome_inc": "Very Awesome Inc"}

Missing file, missing token, or malformed values simply resolve to `None`;
only structurally unreadable files are treated as configuration errors.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from app.sources.errors import SourceConfigurationError

logger = logging.getLogger(__name__)


class BoardRegistry(Protocol):
    def company_for(self, board_token: str) -> str | None: ...


class NullBoardRegistry:
    """Resolves no companies; used when no registry is configured."""

    def company_for(self, board_token: str) -> str | None:
        return None


class FileBoardRegistry:
    """Lazy-loading JSON-file backed registry."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._boards: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._boards is not None:
            return self._boards
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("greenhouse board registry file not found: %s", self._path)
            raw = {}
        except json.JSONDecodeError as exc:
            raise SourceConfigurationError(
                f"board registry file is not valid JSON: {self._path}",
                source="greenhouse",
                cause=exc,
            ) from exc
        except OSError as exc:
            raise SourceConfigurationError(
                f"board registry file could not be read: {self._path}",
                source="greenhouse",
                cause=exc,
            ) from exc
        if not isinstance(raw, dict):
            raise SourceConfigurationError(
                f"board registry must be a flat object of token -> name: {self._path}",
                source="greenhouse",
            )
        boards = {
            str(token): name
            for token, name in raw.items()
            if isinstance(name, str) and name.strip()
        }
        self._boards = boards
        return boards

    def company_for(self, board_token: str) -> str | None:
        return self._load().get(board_token)


def load_board_registry(path: Path | None) -> BoardRegistry:
    """Build the configured registry; `None`/missing path => empty registry."""
    if path is None:
        return NullBoardRegistry()
    return FileBoardRegistry(path)


__all__ = [
    "BoardRegistry",
    "FileBoardRegistry",
    "NullBoardRegistry",
    "load_board_registry",
]
