"""Authentication REST API routes: registration, login, refresh, profile."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import Token, TokenPayload, UserCreate, UserLogin, UserResponse
from app.auth.security import (
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config.settings import get_settings
from app.db.models import UserORM
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    db: Annotated[DBSession, Depends(get_db)],
) -> Token:
    """Register a new user account and return JWT credentials."""
    existing = db.scalar(select(UserORM).where(UserORM.email == payload.email.lower().strip()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = UserORM(
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    settings = get_settings()
    access_token = create_access_token(str(user.id), user.email, settings=settings)
    refresh_token = create_refresh_token(str(user.id), user.email, settings=settings)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=Token)
def login_user(
    payload: UserLogin,
    db: Annotated[DBSession, Depends(get_db)],
) -> Token:
    """Authenticate with email and password and return JWT credentials."""
    user = db.scalar(select(UserORM).where(UserORM.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    settings = get_settings()
    access_token = create_access_token(str(user.id), user.email, settings=settings)
    refresh_token = create_refresh_token(str(user.id), user.email, settings=settings)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=Token)
def refresh_token_endpoint(
    refresh_token: str,
    db: Annotated[DBSession, Depends(get_db)],
) -> Token:
    """Exchange a valid refresh token for a new access and refresh token pair."""
    settings = get_settings()
    try:
        claims: TokenPayload = decode_token(
            refresh_token, expected_type="refresh", settings=settings
        )
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    import uuid

    try:
        user_uuid = uuid.UUID(str(claims.sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in refresh token",
        ) from exc
    user = db.scalar(select(UserORM).where(UserORM.id == user_uuid))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    new_access = create_access_token(str(user.id), user.email, settings=settings)
    new_refresh = create_refresh_token(str(user.id), user.email, settings=settings)

    return Token(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
def get_user_profile(
    current_user: Annotated[UserORM, Depends(get_current_user)],
) -> UserResponse:
    """Get authenticated user's profile."""
    return UserResponse.model_validate(current_user)
