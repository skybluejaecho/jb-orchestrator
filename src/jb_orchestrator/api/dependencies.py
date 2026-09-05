"""FastAPI dependency adapters."""

from typing import cast

from fastapi import Request

from jb_orchestrator.application.budget_services import BudgetService
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.application.model_services import ModelCatalogService
from jb_orchestrator.application.phase_pack_services import PhasePackCatalogService
from jb_orchestrator.application.project_observation_services import ProjectObservationService
from jb_orchestrator.application.request_dispatch_services import RequestDispatchService
from jb_orchestrator.application.services import OrchestrationService
from jb_orchestrator.application.skill_services import SkillCatalogService
from jb_orchestrator.application.workflow_services import WorkflowService
from jb_orchestrator.application.workspace_operation_services import WorkspaceOperationService


def get_orchestration_service(request: Request) -> OrchestrationService:
    """Return the application service owned by this app instance."""

    return cast(OrchestrationService, request.app.state.orchestration_service)


def get_skill_catalog_service(request: Request) -> SkillCatalogService:
    """Return the skill catalog service owned by this app instance."""

    return cast(SkillCatalogService, request.app.state.skill_catalog_service)


def get_model_catalog_service(request: Request) -> ModelCatalogService:
    """Return the model profile catalog service owned by this app instance."""

    return cast(ModelCatalogService, request.app.state.model_catalog_service)


def get_phase_pack_catalog_service(request: Request) -> PhasePackCatalogService:
    """Return the phase-pack catalog service owned by this app instance."""

    return cast(PhasePackCatalogService, request.app.state.phase_pack_catalog_service)


def get_budget_service(request: Request) -> BudgetService:
    """Return the project budget service owned by this app instance."""

    return cast(BudgetService, request.app.state.budget_service)


def get_workflow_service(request: Request) -> WorkflowService:
    """Return the workflow control service owned by this app instance."""

    return cast(WorkflowService, request.app.state.workflow_service)


def get_request_dispatch_service(request: Request) -> RequestDispatchService:
    """Return the project request dispatch service owned by this app instance."""

    return cast(RequestDispatchService, request.app.state.request_dispatch_service)


def get_external_execution_service(request: Request) -> ExternalExecutionService:
    """Return the external execution query service owned by this app instance."""

    return cast(ExternalExecutionService, request.app.state.external_execution_service)


def get_workspace_operation_service(request: Request) -> WorkspaceOperationService:
    """Return the durable workspace command service owned by this app instance."""

    return cast(WorkspaceOperationService, request.app.state.workspace_operation_service)


def get_project_observation_service(request: Request) -> ProjectObservationService:
    """Return the project observation service owned by this app instance."""

    return cast(ProjectObservationService, request.app.state.project_observation_service)
