"""FastAPI application entry point."""

from typing import Final

import uvicorn
from fastapi import FastAPI

from jb_orchestrator import __version__
from jb_orchestrator.config import get_settings

SERVICE_NAME: Final = "jb-orchestrator"


def create_app() -> FastAPI:
    """Build the API application."""

    app = FastAPI(title=SERVICE_NAME, version=__version__)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME, "version": __version__}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app


app = create_app()


def run() -> None:
    """Run the development ASGI server."""

    settings = get_settings()
    uvicorn.run(
        "jb_orchestrator.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
    )
