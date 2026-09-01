"""FastAPI dependency adapters."""

from typing import cast

from fastapi import Request

from jb_orchestrator.application.services import OrchestrationService


def get_orchestration_service(request: Request) -> OrchestrationService:
    """Return the application service owned by this app instance."""

    return cast(OrchestrationService, request.app.state.orchestration_service)
