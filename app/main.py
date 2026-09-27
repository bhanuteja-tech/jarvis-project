"""FastAPI application factory.

Run locally with::

    uvicorn app.main:create_app --factory --reload

The application is created through a factory so tests and future entry
points can inject their own `Settings` (and therefore database URL).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.jarvis import router as jarvis_router
from app.api.routes.llm import router as llm_router
from app.api.routes.voice import router as voice_router
from app.config.settings import Settings, get_settings
from app.db.session import create_db_engine
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve static files for single-page applications with index.html fallback."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code == 404:
                return await super().get_response("index.html", scope)
            return response
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


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
        version="0.2.0",
        description="Job discovery, JD understanding, matching, tailoring "
        "and validation with an agentic Jarvis interface.",
        lifespan=lifespan,
    )

    # Add CORS middleware for React frontend
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(jarvis_router)
    application.include_router(llm_router)
    application.include_router(voice_router)

    # Serve React frontend from build directory if available, otherwise static
    frontend_dir = Path(__file__).resolve().parent / "static" / "dist"
    static_dir = Path(__file__).resolve().parent / "static"

    if frontend_dir.is_dir():
        application.mount(
            "/", SPAStaticFiles(directory=str(frontend_dir), html=True), name="frontend"
        )
    else:
        if static_dir.is_dir():
            application.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    # Available immediately (not only within the lifespan) so probes and
    # tests can access wiring without running startup events.
    application.state.db_engine = engine
    application.state.settings = resolved

    return application


app = create_app()
