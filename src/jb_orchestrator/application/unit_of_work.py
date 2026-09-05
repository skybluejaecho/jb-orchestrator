"""Transaction boundary required by orchestration use cases."""

from types import TracebackType
from typing import Protocol, Self

from jb_orchestrator.artifacts import TaskArtifactRepository
from jb_orchestrator.budgets.repositories import (
    BudgetAccountRepository,
    BudgetReservationRepository,
    UsageRecordRepository,
)
from jb_orchestrator.domain.dispatches import RequestDispatchReceiptRepository
from jb_orchestrator.domain.repositories import (
    EventRepository,
    ProjectRepository,
    RunRepository,
    UserRequestRepository,
)
from jb_orchestrator.external_executions import ExternalExecutionRepository
from jb_orchestrator.model_routing.repositories import ModelProfileRepository
from jb_orchestrator.phase_packs import PhasePackRepository
from jb_orchestrator.scm import ScmPublicationRepository
from jb_orchestrator.security import ServiceAccountRepository
from jb_orchestrator.skills.repositories import SkillRepository
from jb_orchestrator.workflows.bindings import ProjectWorkflowBindingRepository
from jb_orchestrator.workflows.repositories import (
    WorkflowDefinitionRepository,
    WorkflowExecutionRepository,
)
from jb_orchestrator.workspace_operations import WorkspaceOperationRepository


class UnitOfWork(Protocol):
    """Repositories participating in one atomic transaction."""

    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def requests(self) -> UserRequestRepository: ...

    @property
    def request_dispatch_receipts(self) -> RequestDispatchReceiptRepository: ...

    @property
    def runs(self) -> RunRepository: ...

    @property
    def events(self) -> EventRepository: ...

    @property
    def artifacts(self) -> TaskArtifactRepository: ...

    @property
    def skills(self) -> SkillRepository: ...

    @property
    def phase_packs(self) -> PhasePackRepository: ...

    @property
    def model_profiles(self) -> ModelProfileRepository: ...

    @property
    def budget_accounts(self) -> BudgetAccountRepository: ...

    @property
    def budget_reservations(self) -> BudgetReservationRepository: ...

    @property
    def usage_records(self) -> UsageRecordRepository: ...

    @property
    def external_executions(self) -> ExternalExecutionRepository: ...

    @property
    def workspace_operations(self) -> WorkspaceOperationRepository: ...

    @property
    def scm_publications(self) -> ScmPublicationRepository: ...

    @property
    def workflow_definitions(self) -> WorkflowDefinitionRepository: ...

    @property
    def workflow_executions(self) -> WorkflowExecutionRepository: ...

    @property
    def project_workflow_bindings(self) -> ProjectWorkflowBindingRepository: ...

    @property
    def service_accounts(self) -> ServiceAccountRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
