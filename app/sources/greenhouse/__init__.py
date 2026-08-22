"""Greenhouse source adapter package."""

from __future__ import annotations

from app.sources.greenhouse.adapter import GreenhouseAdapter, normalize_job_post
from app.sources.greenhouse.client import GreenhouseClient, validate_board_token
from app.sources.greenhouse.registry import (
    BoardRegistry,
    FileBoardRegistry,
    NullBoardRegistry,
    load_board_registry,
)

__all__ = [
    "BoardRegistry",
    "FileBoardRegistry",
    "GreenhouseAdapter",
    "GreenhouseClient",
    "NullBoardRegistry",
    "load_board_registry",
    "normalize_job_post",
    "validate_board_token",
]
