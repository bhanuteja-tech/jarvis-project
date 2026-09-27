"""FastAPI and WebSocket authentication dependencies."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.schemas import TokenPayload
from app.auth.security import ExpiredTokenError, InvalidTokenError, decode_token
from app.config.settings import Settings, get_settings
from app.db.models import UserORM
from app.db.session import get_db

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


async def get_current_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> TokenPayload:
    """Validate Bearer token from Authorization header and return claims."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(credentials.credentials, expected_type="access")
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    payload: Annotated[TokenPayload, Depends(get_current_token_payload)],
    db: Annotated[DBSession, Depends(get_db)],
) -> UserORM:
    """Resolve authenticated user from database."""
    import uuid

    try:
        user_uuid = uuid.UUID(str(payload.sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        ) from exc
    stmt = select(UserORM).where(UserORM.id == user_uuid)
    user = db.scalar(stmt)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return user


async def authenticate_websocket(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings | None = None,
) -> str:
    """Authenticate a WebSocket connection and return the verified user_id.

    Accepts token via query parameter (?token=...) or Authorization header.
    When jarvis_allow_unauthenticated is True (local dev/test only), missing
    tokens fall back to 'default'. Otherwise, missing or invalid tokens are
    actively rejected with WS code 1008.
    """
    app_settings = getattr(getattr(websocket, "app", None), "state", None)
    app_settings = getattr(app_settings, "settings", None) if app_settings else None
    resolved_settings = settings or app_settings or get_settings()

    raw_token = token if isinstance(token, str) else websocket.query_params.get("token")
    if not raw_token:
        auth_hdr = (
            authorization
            if isinstance(authorization, str)
            else websocket.headers.get("authorization")
        )
        if auth_hdr:
            parts = auth_hdr.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_token = parts[1]

    if not raw_token:
        if resolved_settings.jarvis_allow_unauthenticated:
            logger.debug(
                "WebSocket connected without JWT credentials; defaulting user_id='default' "
                "(gated by jarvis_allow_unauthenticated)"
            )
            return "default"

        logger.warning(
            "WebSocket authentication rejected: missing token and "
            "jarvis_allow_unauthenticated is False"
        )
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    try:
        payload = decode_token(raw_token, expected_type="access", settings=resolved_settings)
        return payload.sub
    except (ExpiredTokenError, InvalidTokenError) as exc:
        logger.warning("WebSocket authentication rejected: %s", exc)
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication token",
        )
        raise
