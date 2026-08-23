"""Site registry: operator-maintained ``site -> company_name`` mapping.

Same architectural principle as the Greenhouse board registry (Decision A):
the public Lever Postings API provides no company name, and we never invent
one from API responses. Company identity comes from operator configuration.

Deliberately NOT consolidated with the Greenhouse registry module during this
step (the Greenhouse implementation is frozen). The structure is a small
Protocol plus one file-backed implementation, replaceable later by a
database-backed implementation without adapter changes.

JSON file format (flat object)::

    {"leverdemo": "Lever Demo Co"}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from app.sources.errors import SourceConfigurationError

logger = logging.getLogger(__name__)


class SiteRegistry(Protocol):
    def company_for(self, site: str) -> str | None: ...


class NullSiteRegistry:
    """Resolves no companies; used when no registry is configured."""

    def company_for(self, site: str) -> str | None:
        return None


class FileSiteRegistry:
    """Lazy-loading JSON-file backed registry."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sites: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._sites is not None:
            return self._sites
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("lever site registry file not found: %s", self._path)
            raw = {}
        except json.JSONDecodeError as exc:
            raise SourceConfigurationError(
                f"site registry file is not valid JSON: {self._path}",
                source="lever",
                cause=exc,
            ) from exc
        except OSError as exc:
            raise SourceConfigurationError(
                f"site registry file could not be read: {self._path}",
                source="lever",
                cause=exc,
            ) from exc
        if not isinstance(raw, dict):
            raise SourceConfigurationError(
                f"site registry must be a flat object of site -> name: {self._path}",
                source="lever",
            )
        sites = {
            str(site): name for site, name in raw.items() if isinstance(name, str) and name.strip()
        }
        self._sites = sites
        return sites

    def company_for(self, site: str) -> str | None:
        return self._load().get(site)


def load_site_registry(path: Path | None) -> SiteRegistry:
    """Build the configured registry; ``None``/missing path => empty registry."""
    if path is None:
        return NullSiteRegistry()
    return FileSiteRegistry(path)


__all__ = [
    "FileSiteRegistry",
    "NullSiteRegistry",
    "SiteRegistry",
    "load_site_registry",
]
