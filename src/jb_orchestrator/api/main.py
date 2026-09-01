"""FastAPI application entry point."""

from typing import Final

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from jb_orchestrator import __version__
from jb_orchestrator.api.routes import router
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.services import OrchestrationService
from jb_orchestrator.config import get_settings
from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory

SERVICE_NAME: Final = "jb-orchestrator"


def create_app(service: OrchestrationService | None = None) -> FastAPI:
    """Build the API application."""

    app = FastAPI(title=SERVICE_NAME, version=__version__)
    if service is None:
        session_factory = create_session_factory()
        service = OrchestrationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    app.state.orchestration_service = service

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME, "version": __version__}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    app.include_router(router)

    def problem(status_code: int, title: str, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "type": "about:blank",
                "title": title,
                "status": status_code,
                "detail": detail,
            },
        )

    @app.exception_handler(ResourceNotFound)
    async def not_found_handler(_: Request, exc: ResourceNotFound) -> JSONResponse:
        return problem(status.HTTP_404_NOT_FOUND, "Resource not found", str(exc))

    @app.exception_handler(ResourceConflict)
    async def conflict_handler(_: Request, exc: ResourceConflict) -> JSONResponse:
        return problem(status.HTTP_409_CONFLICT, "Resource conflict", str(exc))

    @app.exception_handler(InvalidStateTransition)
    async def transition_handler(_: Request, exc: InvalidStateTransition) -> JSONResponse:
        return problem(status.HTTP_409_CONFLICT, "Invalid state transition", str(exc))

    @app.exception_handler(DomainValidationError)
    async def validation_handler(_: Request, exc: DomainValidationError) -> JSONResponse:
        return problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "Domain validation failed", str(exc))

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
