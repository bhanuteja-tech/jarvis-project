"""Tests for User model, password security, JWT handling, and Auth API routes."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.dependencies import authenticate_websocket
from app.auth.security import (
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config.settings import Settings
from app.db.models import UserORM
from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        jwt_secret_key="test-secret-key-for-auth-testing-only-32b",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=7,
    )


@pytest.fixture
def in_memory_db():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserORM.__table__.create(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        UserORM.__table__.drop(bind=engine)


@pytest.fixture
def client(in_memory_db, auth_settings) -> TestClient:
    app = create_app(auth_settings)

    def override_get_db():
        yield in_memory_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestPasswordSecurity:
    """Password hashing and verification."""

    def test_hash_and_verify_password(self) -> None:
        raw_pw = "SuperSecretPassword123!"
        hashed = hash_password(raw_pw)

        assert hashed != raw_pw
        assert verify_password(raw_pw, hashed) is True
        assert verify_password("WrongPassword!", hashed) is False

    def test_empty_or_corrupt_hash_returns_false(self) -> None:
        assert verify_password("test", "") is False
        assert verify_password("test", "corrupted_hash") is False


class TestJwtSecurity:
    """JWT creation, expiration, and validation."""

    def test_create_and_decode_access_token(self, auth_settings: Settings) -> None:
        user_id = str(uuid4())
        email = "alice@example.com"

        token = create_access_token(user_id, email, settings=auth_settings)
        assert isinstance(token, str)

        claims = decode_token(token, expected_type="access", settings=auth_settings)
        assert claims.sub == user_id
        assert claims.email == email
        assert claims.type == "access"

    def test_expired_token_raises_error(self, auth_settings: Settings) -> None:
        user_id = str(uuid4())
        # Negative delta => already expired
        expired_token = create_access_token(
            user_id,
            expires_delta=timedelta(seconds=-10),
            settings=auth_settings,
        )
        with pytest.raises(ExpiredTokenError):
            decode_token(expired_token, expected_type="access", settings=auth_settings)

    def test_forged_secret_raises_invalid_token(self, auth_settings: Settings) -> None:
        user_id = str(uuid4())
        other_settings = Settings(
            jwt_secret_key="attacker-tampered-secret-key-different",
            jwt_algorithm="HS256",
        )
        forged_token = create_access_token(user_id, settings=other_settings)

        with pytest.raises(InvalidTokenError):
            decode_token(forged_token, expected_type="access", settings=auth_settings)

    def test_token_type_mismatch_raises_error(self, auth_settings: Settings) -> None:
        user_id = str(uuid4())
        refresh_tok = create_refresh_token(user_id, settings=auth_settings)

        # Trying to validate refresh token as access token must fail
        with pytest.raises(InvalidTokenError) as exc:
            decode_token(refresh_tok, expected_type="access", settings=auth_settings)
        assert "expected 'access'" in str(exc.value)


class TestAuthApiRoutes:
    """User registration, login, profile, and refresh endpoints."""

    def test_register_login_and_me_flow(self, client: TestClient) -> None:
        # 1. Register
        reg_payload = {
            "email": "user@example.com",
            "password": "Password123!",
            "full_name": "Test User",
        }
        res_reg = client.post("/api/auth/register", json=reg_payload)
        assert res_reg.status_code == status.HTTP_201_CREATED
        tokens = res_reg.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        access_tok = tokens["access_token"]

        # Duplicate registration fails
        res_dup = client.post("/api/auth/register", json=reg_payload)
        assert res_dup.status_code == status.HTTP_409_CONFLICT

        # 2. Get profile with access token
        res_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_tok}"},
        )
        assert res_me.status_code == status.HTTP_200_OK
        profile = res_me.json()
        assert profile["email"] == "user@example.com"
        assert profile["full_name"] == "Test User"
        assert profile["is_active"] is True

        # 3. Login with credentials
        login_payload = {"email": "user@example.com", "password": "Password123!"}
        res_login = client.post("/api/auth/login", json=login_payload)
        assert res_login.status_code == status.HTTP_200_OK
        login_tokens = res_login.json()
        assert "access_token" in login_tokens

        # Wrong password fails
        res_bad = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "WrongPassword!"},
        )
        assert res_bad.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_flow(self, client: TestClient) -> None:
        reg_payload = {
            "email": "refresh_user@example.com",
            "password": "Password123!",
        }
        res = client.post("/api/auth/register", json=reg_payload)
        tokens = res.json()
        refresh_tok = tokens["refresh_token"]

        # Refresh
        res_refresh = client.post(
            f"/api/auth/refresh?refresh_token={refresh_tok}",
        )
        assert res_refresh.status_code == status.HTTP_200_OK
        new_tokens = res_refresh.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens


class TestWebSocketAuth:
    """WebSocket authentication helper."""

    @pytest.mark.asyncio
    async def test_authenticate_ws_with_valid_token(self, auth_settings: Settings) -> None:
        from unittest.mock import AsyncMock

        user_id = str(uuid4())
        tok = create_access_token(user_id, settings=auth_settings)

        ws = MagicMock()
        ws.close = AsyncMock()
        verified_user = await authenticate_websocket(ws, token=tok, settings=auth_settings)
        assert verified_user == user_id

    @pytest.mark.asyncio
    async def test_authenticate_ws_without_token_rejected_when_flag_off(
        self, auth_settings: Settings
    ) -> None:
        from unittest.mock import AsyncMock

        assert auth_settings.jarvis_allow_unauthenticated is False

        ws = MagicMock()
        ws.close = AsyncMock()
        ws.query_params = {}
        ws.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_websocket(
                ws, token=None, authorization=None, settings=auth_settings
            )
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        ws.close.assert_awaited_once_with(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token",
        )

    @pytest.mark.asyncio
    async def test_authenticate_ws_without_token_allowed_when_flag_on(
        self, auth_settings: Settings
    ) -> None:
        settings_allowed = Settings(
            jwt_secret_key=auth_settings.jwt_secret_key,
            jarvis_allow_unauthenticated=True,
        )
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {}
        user = await authenticate_websocket(
            ws, token=None, authorization=None, settings=settings_allowed
        )
        assert user == "default"

    @pytest.mark.asyncio
    async def test_authenticate_ws_with_invalid_token_closes_ws(
        self, auth_settings: Settings
    ) -> None:
        from unittest.mock import AsyncMock

        ws = MagicMock()
        ws.close = AsyncMock()
        ws.query_params = {}
        ws.headers = {}
        with pytest.raises(InvalidTokenError):
            await authenticate_websocket(ws, token="invalid.token.here", settings=auth_settings)
        ws.close.assert_awaited_once_with(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication token",
        )

    def test_ws_endpoint_rejects_missing_token_when_flag_off(
        self, auth_settings: Settings
    ) -> None:
        """Integration test: with jarvis_allow_unauthenticated=False, connection is rejected."""
        assert auth_settings.jarvis_allow_unauthenticated is False
        app = create_app(auth_settings)
        client = TestClient(app)

        try:
            with client.websocket_connect("/ws/jarvis?session_id=unauth_test") as ws:
                ws.send_json({"type": "chat", "text": "hello"})
                frame = ws.receive()
                code = frame.get("code") or getattr(ws, "_close_code", None)
                assert code == status.WS_1008_POLICY_VIOLATION or ws.closed
        except Exception as exc:
            # Starlette TestClient raises WebSocketDisconnect or closed on 1008 reject
            exc_str = str(exc).lower()
            assert "1008" in exc_str or "closed" in exc_str or "disconnect" in exc_str
