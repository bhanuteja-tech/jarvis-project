"""FastAPI application factory.

Run locally with::

    uvicorn app.main:create_app --factory --reload

The application is created through a factory so tests and future entry
points can inject their own `Settings` (and therefore database URL).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.config.settings import Settings, get_settings
from app.db.session import create_db_engine
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    engine = create_db_engine(resolved.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logger.info("application starting up")
        try:
            yield
        finally:
            logger.info("disposing database engine")
            engine.dispose()

    application = FastAPI(
        title="Jarvis Job Discovery",
        version="0.1.0",
        description="Phase 1 foundation: job discovery source adapters.",
        lifespan=lifespan,
    )
    application.include_router(health_router)

    # Available immediately (not only within the lifespan) so probes and
    # tests can access wiring without running startup events.
    application.state.db_engine = engine
    application.state.settings = resolved

    return application


app = create_app()
