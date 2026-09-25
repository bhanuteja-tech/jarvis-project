"""Credential Vault for local desktop and web service credentials.

Stores user credentials (e.g. GitHub username/handle, LinkedIn profile, etc.)
in a local, protected JSON file at `~/.jarvis/credentials.json`.
Never commits or exposes secrets.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_VAULT_DIR = Path.home() / ".jarvis"
DEFAULT_VAULT_FILE = DEFAULT_VAULT_DIR / "credentials.json"


class CredentialVault:
    """Manages locally stored credentials for desktop/web automation."""

    def __init__(self, vault_path: Path | str | None = None) -> None:
        if vault_path is not None:
            self._path = Path(vault_path)
        else:
            self._path = DEFAULT_VAULT_FILE

    def _ensure_dir(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("could not create vault directory %s: %s", self._path.parent, exc)

    def _load(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("failed to load credentials from %s: %s", self._path, exc)
            return {}

    def _save(self, data: dict[str, Any]) -> bool:
        self._ensure_dir()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except OSError as exc:
            logger.error("failed to save credentials to %s: %s", self._path, exc)
            return False

    def get(self, service: str) -> dict[str, Any] | None:
        """Get credentials for a given service (e.g. 'github')."""
        key = (service or "").strip().lower()
        data = self._load()
        creds = data.get(key)
        return creds if isinstance(creds, dict) else None

    def get_field(self, service: str, field: str, default: Any = None) -> Any:
        """Get a specific field (e.g. 'username') for a service."""
        creds = self.get(service)
        if creds is None:
            return default
        return creds.get(field, default)

    def set(self, service: str, creds: dict[str, Any]) -> bool:
        """Store or update credentials for a given service."""
        key = (service or "").strip().lower()
        if not key:
            return False
        data = self._load()
        existing = data.get(key, {})
        if isinstance(existing, dict):
            existing.update(creds)
            data[key] = existing
        else:
            data[key] = creds
        return self._save(data)

    def set_field(self, service: str, field: str, value: Any) -> bool:
        """Set a single field (e.g. username) for a service."""
        return self.set(service, {field: value})

    def has(self, service: str, required_field: str | None = None) -> bool:
        """Check if credentials exist for a service (and optionally a required field)."""
        creds = self.get(service)
        if creds is None:
            return False
        if required_field is not None:
            val = creds.get(required_field)
            return bool(val and str(val).strip())
        return len(creds) > 0

    def delete(self, service: str) -> bool:
        """Delete credentials for a service."""
        key = (service or "").strip().lower()
        data = self._load()
        if key in data:
            del data[key]
            return self._save(data)
        return False

    def list_services(self) -> list[str]:
        """List all services with stored credentials."""
        data = self._load()
        return [k for k, v in data.items() if isinstance(v, dict) and v]


# Global shared instance
default_vault = CredentialVault()

__all__ = ["CredentialVault", "default_vault"]
