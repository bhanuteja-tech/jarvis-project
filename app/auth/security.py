"""Security and cryptography utilities: password hashing and JWT token handling."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.auth.schemas import TokenPayload
from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class AuthSecurityError(Exception):
    """Base exception for authentication errors."""


class InvalidTokenError(AuthSecurityError):
    """Token is invalid, malformed, or signature verification failed."""


class ExpiredTokenError(AuthSecurityError):
    """Token has expired."""


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt."""
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning("Password verification failed unexpectedly: %s", exc)
        return False


def create_access_token(
    user_id: str,
    email: str | None = None,
    *,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token."""
    cfg = settings or get_settings()
    secret = cfg.jwt_secret_key.get_secret_value()
    algorithm = cfg.jwt_algorithm

    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=cfg.jwt_access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_refresh_token(
    user_id: str,
    email: str | None = None,
    *,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT refresh token."""
    cfg = settings or get_settings()
    secret = cfg.jwt_secret_key.get_secret_value()
    algorithm = cfg.jwt_algorithm

    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=cfg.jwt_refresh_token_expire_days)
    )

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": "refresh",
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(
    token: str,
    expected_type: str = "access",
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and verify a signed JWT token."""
    cfg = settings or get_settings()
    secret = cfg.jwt_secret_key.get_secret_value()
    algorithm = cfg.jwt_algorithm

    try:
        raw_payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(f"Could not validate credentials: {exc}") from exc

    token_type = raw_payload.get("type", "access")
    if token_type != expected_type:
        raise InvalidTokenError(
            f"Invalid token type: expected '{expected_type}', got '{token_type}'"
        )

    return TokenPayload(
        sub=raw_payload["sub"],
        email=raw_payload.get("email"),
        type=token_type,
        exp=raw_payload.get("exp"),
    )
