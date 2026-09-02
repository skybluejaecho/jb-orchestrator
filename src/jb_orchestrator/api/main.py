"""FastAPI application entry point."""

from typing import Final

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from jb_orchestrator import __version__
from jb_orchestrator.api.routes import router
from jb_orchestrator.application.budget_services import BudgetService
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.application.model_services import ModelCatalogService
from jb_orchestrator.application.services import OrchestrationService
from jb_orchestrator.application.skill_services import SkillCatalogService
from jb_orchestrator.application.workflow_services import WorkflowService
from jb_orchestrator.config import get_settings
from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.workflows import WorkflowDefinitionError

SERVICE_NAME: Final = "jb-orchestrator"


def create_app(
    service: OrchestrationService | None = None,
    skill_service: SkillCatalogService | None = None,
    model_service: ModelCatalogService | None = None,
    budget_service: BudgetService | None = None,
    workflow_service: WorkflowService | None = None,
    external_execution_service: ExternalExecutionService | None = None,
) -> FastAPI:
    """Build the API application."""

    app = FastAPI(title=SERVICE_NAME, version=__version__)
    if (
        service is None
        or skill_service is None
        or model_service is None
        or budget_service is None
        or workflow_service is None
        or external_execution_service is None
    ):
        session_factory = create_session_factory()
    if service is None:
        service = OrchestrationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    if skill_service is None:
        skill_service = SkillCatalogService(lambda: SqlAlchemyUnitOfWork(session_factory))
    if model_service is None:
        model_service = ModelCatalogService(lambda: SqlAlchemyUnitOfWork(session_factory))
    if budget_service is None:
        budget_service = BudgetService(lambda: SqlAlchemyUnitOfWork(session_factory))
    if workflow_service is None:
        workflow_service = WorkflowService(lambda: SqlAlchemyUnitOfWork(session_factory))
    if external_execution_service is None:
        external_execution_service = ExternalExecutionService(
            lambda: SqlAlchemyUnitOfWork(session_factory)
        )
    app.state.orchestration_service = service
    app.state.skill_catalog_service = skill_service
    app.state.model_catalog_service = model_service
    app.state.budget_service = budget_service
    app.state.workflow_service = workflow_service
    app.state.external_execution_service = external_execution_service

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

    @app.exception_handler(WorkflowDefinitionError)
    async def workflow_validation_handler(_: Request, exc: WorkflowDefinitionError) -> JSONResponse:
        return problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Workflow definition validation failed",
            str(exc),
        )

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
