"""Credential Vault for local desktop and web service credentials.

Multi-tenant architecture:
- Each user's credentials are encrypted at rest using Fernet symmetric encryption.
- Queries are strictly scoped per-tenant by user_id.
- BaseCredentialVault defines the abstract interface.
- PostgresCredentialVault persists encrypted payloads in PostgreSQL (UserCredentialORM).
- EncryptedMemoryCredentialVault provides encrypted in-memory storage for testing and local mode.
- CredentialVault maintains backward-compatibility for file-based test fixtures.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet
from pydantic import SecretStr

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

DEFAULT_VAULT_DIR = Path.home() / ".jarvis"
DEFAULT_VAULT_FILE = DEFAULT_VAULT_DIR / "credentials.json"


def get_fernet_key(key_material: str | bytes | SecretStr | None = None) -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from arbitrary secret input."""
    raw: str | bytes = ""
    if key_material is not None:
        if isinstance(key_material, SecretStr):
            raw = key_material.get_secret_value()
        else:
            raw = key_material

    if not raw:
        try:
            from app.config.settings import get_settings

            settings_key = get_settings().jarvis_vault_secret_key
            if settings_key:
                raw = settings_key.get_secret_value()
        except Exception:
            pass

    if not raw:
        # Consistent dev/test fallback key
        digest = hashlib.sha256(b"jarvis-dev-vault-secret-key-salt").digest()
        return base64.urlsafe_b64encode(digest)

    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    # If already a valid Fernet key (32 url-safe base64 bytes)
    try:
        Fernet(raw_bytes)
        return raw_bytes
    except Exception:
        digest = hashlib.sha256(raw_bytes).digest()
        return base64.urlsafe_b64encode(digest)


class BaseCredentialVault(ABC):
    """Abstract interface for user-scoped credential vaults."""

    def __init__(self, user_id: str) -> None:
        clean_user = (user_id or "").strip()
        if not clean_user:
            raise ValueError("user_id is required and cannot be empty for BaseCredentialVault")
        self.user_id = clean_user

    @abstractmethod
    def get(self, service: str) -> dict[str, Any] | None:
        """Get decrypted credentials for a given service."""

    @abstractmethod
    def get_field(self, service: str, field: str, default: Any = None) -> Any:
        """Get a specific field (e.g. 'username') for a service."""

    @abstractmethod
    def set(self, service: str, creds: dict[str, Any]) -> bool:
        """Store or update credentials for a given service."""

    @abstractmethod
    def set_field(self, service: str, field: str, value: Any) -> bool:
        """Set a single field for a service."""

    @abstractmethod
    def has(self, service: str, required_field: str | None = None) -> bool:
        """Check if credentials exist for a service."""

    @abstractmethod
    def delete(self, service: str) -> bool:
        """Delete credentials for a service."""

    @abstractmethod
    def list_services(self) -> list[str]:
        """List all services with stored credentials for this user."""


class EncryptedMemoryCredentialVault(BaseCredentialVault):
    """In-memory encrypted credential vault for tests, dev, or offline operation."""

    def __init__(
        self,
        user_id: str = "default",
        encryption_key: str | bytes | SecretStr | None = None,
    ) -> None:
        super().__init__(user_id=user_id)
        self._fernet = Fernet(get_fernet_key(encryption_key))
        self._store: dict[str, bytes] = {}

    def get(self, service: str) -> dict[str, Any] | None:
        key = (service or "").strip().lower()
        if not key or key not in self._store:
            return None
        try:
            decrypted = self._fernet.decrypt(self._store[key])
            data = json.loads(decrypted.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning(
                "Failed to decrypt credentials for user=%s service=%s: %s",
                self.user_id,
                service,
                exc,
            )
            return None

    def get_field(self, service: str, field: str, default: Any = None) -> Any:
        creds = self.get(service)
        if creds is None:
            return default
        return creds.get(field, default)

    def set(self, service: str, creds: dict[str, Any]) -> bool:
        key = (service or "").strip().lower()
        if not key:
            return False
        existing = self.get(service) or {}
        merged = {**existing, **creds}
        try:
            serialized = json.dumps(merged).encode("utf-8")
            self._store[key] = self._fernet.encrypt(serialized)
            return True
        except Exception as exc:
            logger.error(
                "Failed to store credentials for user=%s service=%s: %s",
                self.user_id,
                service,
                exc,
            )
            return False

    def set_field(self, service: str, field: str, value: Any) -> bool:
        return self.set(service, {field: value})

    def has(self, service: str, required_field: str | None = None) -> bool:
        creds = self.get(service)
        if creds is None:
            return False
        if required_field is not None:
            val = creds.get(required_field)
            return bool(val and str(val).strip())
        return len(creds) > 0

    def delete(self, service: str) -> bool:
        key = (service or "").strip().lower()
        if key in self._store:
            del self._store[key]
            return True
        return False

    def list_services(self) -> list[str]:
        return sorted(self._store.keys())


class PostgresCredentialVault(BaseCredentialVault):
    """PostgreSQL-backed credential vault with Fernet symmetric encryption.

    All queries are strictly scoped by user_id. Decrypted payloads are only returned
    to explicit callers and never logged or serialized to state/LLM prompts.
    """

    def __init__(
        self,
        user_id: str,
        db_session: Session | None = None,
        session_factory: sessionmaker[Session] | None = None,
        encryption_key: str | bytes | SecretStr | None = None,
    ) -> None:
        super().__init__(user_id=user_id)
        self.db_session = db_session
        self.session_factory = session_factory
        self._fernet = Fernet(get_fernet_key(encryption_key))

    def _get_session(self) -> Any:
        if self.db_session is not None:
            from contextlib import nullcontext

            return nullcontext(self.db_session)
        if self.session_factory is not None:
            from app.db.session import session_scope

            return session_scope(self.session_factory)
        raise RuntimeError("PostgresCredentialVault requires either db_session or session_factory")

    def get(self, service: str) -> dict[str, Any] | None:
        key = (service or "").strip().lower()
        if not key:
            return None
        from sqlalchemy import select

        from app.db.models import UserCredentialORM

        try:
            with self._get_session() as session:
                stmt = select(UserCredentialORM).where(
                    UserCredentialORM.user_id == self.user_id,
                    UserCredentialORM.service == key,
                )
                row = session.execute(stmt).scalar_one_or_none()
                if row is None or not row.encrypted_payload:
                    return None
                decrypted = self._fernet.decrypt(row.encrypted_payload)
                data = json.loads(decrypted.decode("utf-8"))
                return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning(
                "PostgresCredentialVault.get failed for user=%s service=%s: %s",
                self.user_id,
                key,
                exc,
            )
            return None

    def get_field(self, service: str, field: str, default: Any = None) -> Any:
        creds = self.get(service)
        if creds is None:
            return default
        return creds.get(field, default)

    def set(self, service: str, creds: dict[str, Any]) -> bool:
        key = (service or "").strip().lower()
        if not key:
            return False
        from sqlalchemy import select

        from app.db.models import UserCredentialORM

        try:
            existing = self.get(service) or {}
            merged = {**existing, **creds}
            serialized = json.dumps(merged).encode("utf-8")
            encrypted = self._fernet.encrypt(serialized)

            with self._get_session() as session:
                stmt = select(UserCredentialORM).where(
                    UserCredentialORM.user_id == self.user_id,
                    UserCredentialORM.service == key,
                )
                row = session.execute(stmt).scalar_one_or_none()
                if row is not None:
                    row.encrypted_payload = encrypted
                else:
                    new_row = UserCredentialORM(
                        user_id=self.user_id,
                        service=key,
                        encrypted_payload=encrypted,
                    )
                    session.add(new_row)
                if self.db_session is not None:
                    session.commit()
            return True
        except Exception as exc:
            logger.error(
                "PostgresCredentialVault.set failed for user=%s service=%s: %s",
                self.user_id,
                key,
                exc,
            )
            return False

    def set_field(self, service: str, field: str, value: Any) -> bool:
        return self.set(service, {field: value})

    def has(self, service: str, required_field: str | None = None) -> bool:
        creds = self.get(service)
        if creds is None:
            return False
        if required_field is not None:
            val = creds.get(required_field)
            return bool(val and str(val).strip())
        return len(creds) > 0

    def delete(self, service: str) -> bool:
        key = (service or "").strip().lower()
        if not key:
            return False
        from sqlalchemy import delete

        from app.db.models import UserCredentialORM

        try:
            with self._get_session() as session:
                stmt = delete(UserCredentialORM).where(
                    UserCredentialORM.user_id == self.user_id,
                    UserCredentialORM.service == key,
                )
                res = session.execute(stmt)
                if self.db_session is not None:
                    session.commit()
                return bool(res.rowcount and res.rowcount > 0)
        except Exception as exc:
            logger.error(
                "PostgresCredentialVault.delete failed for user=%s service=%s: %s",
                self.user_id,
                key,
                exc,
            )
            return False

    def list_services(self) -> list[str]:
        from sqlalchemy import select

        from app.db.models import UserCredentialORM

        try:
            with self._get_session() as session:
                stmt = select(UserCredentialORM.service).where(
                    UserCredentialORM.user_id == self.user_id
                ).order_by(UserCredentialORM.service)
                rows = session.execute(stmt).scalars().all()
                return list(rows)
        except Exception as exc:
            logger.error(
                "PostgresCredentialVault.list_services failed for user=%s: %s",
                self.user_id,
                exc,
            )
            return []


class CredentialVault(BaseCredentialVault):
    """File-backed credential vault for backward compatibility with local tests.

    Warning: Unencrypted storage. In production multi-tenant environments,
    PostgresCredentialVault MUST be used instead.
    """

    def __init__(self, vault_path: Path | str | None = None, user_id: str = "default") -> None:
        super().__init__(user_id=user_id)
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
        key = (service or "").strip().lower()
        data = self._load()
        creds = data.get(key)
        return creds if isinstance(creds, dict) else None

    def get_field(self, service: str, field: str, default: Any = None) -> Any:
        creds = self.get(service)
        if creds is None:
            return default
        return creds.get(field, default)

    def set(self, service: str, creds: dict[str, Any]) -> bool:
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
        return self.set(service, {field: value})

    def has(self, service: str, required_field: str | None = None) -> bool:
        creds = self.get(service)
        if creds is None:
            return False
        if required_field is not None:
            val = creds.get(required_field)
            return bool(val and str(val).strip())
        return len(creds) > 0

    def delete(self, service: str) -> bool:
        key = (service or "").strip().lower()
        data = self._load()
        if key in data:
            del data[key]
            return self._save(data)
        return False

    def list_services(self) -> list[str]:
        data = self._load()
        return sorted([k for k, v in data.items() if isinstance(v, dict) and v])


# Shared fallback instance for legacy code paths (marked for migration)
default_vault = EncryptedMemoryCredentialVault(user_id="default")

__all__ = [
    "BaseCredentialVault",
    "CredentialVault",
    "EncryptedMemoryCredentialVault",
    "PostgresCredentialVault",
    "default_vault",
    "get_fernet_key",
]
