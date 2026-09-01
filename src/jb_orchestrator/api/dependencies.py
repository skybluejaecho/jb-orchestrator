"""FastAPI dependency adapters."""

from typing import cast

from fastapi import Request

from jb_orchestrator.application.services import OrchestrationService
from jb_orchestrator.application.skill_services import SkillCatalogService


def get_orchestration_service(request: Request) -> OrchestrationService:
    """Return the application service owned by this app instance."""

    return cast(OrchestrationService, request.app.state.orchestration_service)


def get_skill_catalog_service(request: Request) -> SkillCatalogService:
    """Return the skill catalog service owned by this app instance."""

    return cast(SkillCatalogService, request.app.state.skill_catalog_service)
