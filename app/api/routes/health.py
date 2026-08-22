"""Health and readiness endpoints.

`/healthz` is a liveness probe with no dependencies.
`/readyz` verifies database connectivity. The check is a FastAPI dependency
so tests (and future wiring) can override it without touching the route.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _database_healthy(request: Request) -> bool:
    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        return False
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception:
        logger.warning("database readiness probe failed", exc_info=True)
        return False
    return True


@router.get("/healthz")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readiness(
    database_healthy: bool = Depends(_database_healthy),
) -> Response:
    if not database_healthy:
        return Response(
            content='{"status":"not_ready","database":"unavailable"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    return Response(
        content='{"status":"ready","database":"ok"}',
        media_type="application/json",
    )
