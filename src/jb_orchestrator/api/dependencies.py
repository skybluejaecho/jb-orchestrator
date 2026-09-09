"""FastAPI dependency adapters."""

from typing import cast

from fastapi import HTTPException, Request, status

from jb_orchestrator.application.budget_services import BudgetService
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.application.model_services import ModelCatalogService
from jb_orchestrator.application.notification_services import NotificationService
from jb_orchestrator.application.phase_pack_services import PhasePackCatalogService
from jb_orchestrator.application.project_observation_services import ProjectObservationService
from jb_orchestrator.application.request_dispatch_services import RequestDispatchService
from jb_orchestrator.application.scm_publication_services import ScmPublicationService
from jb_orchestrator.application.security_services import SecurityService
from jb_orchestrator.application.services import OrchestrationService
from jb_orchestrator.application.skill_services import SkillCatalogService
from jb_orchestrator.application.worker_presence_services import WorkerPresenceService
from jb_orchestrator.application.worker_readiness_services import WorkerReadinessService
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


def get_scm_publication_service(request: Request) -> ScmPublicationService:
    """Return the durable SCM publication service owned by this app instance."""

    return cast(ScmPublicationService, request.app.state.scm_publication_service)


def get_project_observation_service(request: Request) -> ProjectObservationService:
    """Return the project observation service owned by this app instance."""

    return cast(ProjectObservationService, request.app.state.project_observation_service)


def get_worker_presence_service(request: Request) -> WorkerPresenceService:
    """Return the durable worker presence service owned by this app instance."""

    return cast(WorkerPresenceService, request.app.state.worker_presence_service)


def get_worker_readiness_service(request: Request) -> WorkerReadinessService:
    """Return the project worker-readiness diagnostic service."""

    return cast(WorkerReadinessService, request.app.state.worker_readiness_service)


def get_notification_service(request: Request) -> NotificationService:
    """Return the project notification configuration and outbox service."""

    return cast(NotificationService, request.app.state.notification_service)


def get_security_service(request: Request) -> SecurityService:
    """Return authentication management only when bearer security is enabled."""

    service = request.app.state.security_service
    if not request.app.state.auth_enabled or service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service-account credential management requires API authentication",
        )
    return cast(SecurityService, service)
