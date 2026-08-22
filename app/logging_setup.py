"""Application logging setup.

Uses the Python standard library. Contextual details (source, endpoint,
attempt, status, duration, counts) are embedded directly into messages by the
emitting modules using consistent `key=value` fragments. Secrets are never
logged anywhere in this codebase.
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    resolved = getattr(logging, level.upper(), None)
    if not isinstance(resolved, int):
        raise ValueError(f"Invalid log level: {level!r}")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(resolved)
