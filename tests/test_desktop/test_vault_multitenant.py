"""Multi-tenant isolation and encryption tests for CredentialVault."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import UserCredentialORM
from app.desktop.vault import (
    EncryptedMemoryCredentialVault,
    PostgresCredentialVault,
)


class TestEncryptedMemoryCredentialVault:
    def test_user_id_is_required(self) -> None:
        with pytest.raises(ValueError, match="user_id is required"):
            EncryptedMemoryCredentialVault(user_id="")

    def test_encryption_at_rest(self) -> None:
        vault = EncryptedMemoryCredentialVault(user_id="user_123")
        vault.set("github", {"username": "alice", "token": "ghp_alice_secret"})

        # Check internal store is encrypted
        assert "github" in vault._store
        raw_payload = vault._store["github"]
        assert isinstance(raw_payload, bytes)
        assert b"ghp_alice_secret" not in raw_payload
        assert b"alice" not in raw_payload

        # Decrypted retrieval works
        creds = vault.get("github")
        assert creds == {"username": "alice", "token": "ghp_alice_secret"}

    def test_user_isolation(self) -> None:
        vault_a = EncryptedMemoryCredentialVault(user_id="user_a")
        vault_b = EncryptedMemoryCredentialVault(user_id="user_b")

        vault_a.set("slack", {"token": "xoxb-alice-token"})
        vault_b.set("slack", {"token": "xoxb-bob-token"})

        assert vault_a.get_field("slack", "token") == "xoxb-alice-token"
        assert vault_b.get_field("slack", "token") == "xoxb-bob-token"

        assert vault_a.delete("slack") is True
        assert vault_a.has("slack") is False
        assert vault_b.has("slack") is True
        assert vault_b.get_field("slack", "token") == "xoxb-bob-token"


class TestPostgresCredentialVault:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("sqlite:///:memory:")
        UserCredentialORM.__table__.create(engine)
        maker = sessionmaker(bind=engine, expire_on_commit=False)
        with maker() as session:
            yield session
        UserCredentialORM.__table__.drop(engine)

    def test_postgres_vault_isolation_and_encryption(self, db_session) -> None:
        vault_a = PostgresCredentialVault(user_id="tenant_a", db_session=db_session)
        vault_b = PostgresCredentialVault(user_id="tenant_b", db_session=db_session)

        vault_a.set("aws", {"access_key": "AKIA_ALICE", "secret": "secret_alice"})
        vault_b.set("aws", {"access_key": "AKIA_BOB", "secret": "secret_bob"})

        # Verify DB rows
        rows = db_session.query(UserCredentialORM).all()
        assert len(rows) == 2
        for r in rows:
            assert isinstance(r.encrypted_payload, bytes)
            assert b"secret_alice" not in r.encrypted_payload
            assert b"secret_bob" not in r.encrypted_payload

        # Tenant A sees only Alice's creds
        assert vault_a.get_field("aws", "access_key") == "AKIA_ALICE"
        assert vault_a.list_services() == ["aws"]

        # Tenant B sees only Bob's creds
        assert vault_b.get_field("aws", "access_key") == "AKIA_BOB"
        assert vault_b.list_services() == ["aws"]

        # Deleting from Tenant A does not touch Tenant B
        assert vault_a.delete("aws") is True
        assert vault_a.has("aws") is False
        assert vault_b.has("aws") is True
        assert vault_b.get_field("aws", "access_key") == "AKIA_BOB"
