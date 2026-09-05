"""In-memory application adapters used by tests."""

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.budgets import (
    BudgetAccount,
    BudgetReservation,
    BudgetReservationStatus,
    UsageRecord,
)
from jb_orchestrator.domain import (
    DomainEvent,
    Project,
    ProjectStatus,
    RequestDispatchReceipt,
    RequestStatus,
    Run,
    RunStatus,
    UserRequest,
)
from jb_orchestrator.external_executions import ExternalExecution, ExternalExecutionStatus
from jb_orchestrator.model_routing import ModelProfile
from jb_orchestrator.phase_packs import PhasePackDefinition
from jb_orchestrator.scm import ScmPublication, ScmPublicationStatus
from jb_orchestrator.security import ServiceAccount
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import (
    NodeExecutionStatus,
    ProjectWorkflowBinding,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowTaskCandidate,
)
from jb_orchestrator.workspace_operations import (
    WorkspaceOperation,
    WorkspaceOperationStatus,
)


@dataclass
class MemoryStore:
    projects: dict[UUID, Project] = field(default_factory=dict)
    requests: dict[UUID, UserRequest] = field(default_factory=dict)
    request_dispatch_receipts: dict[tuple[UUID, str, str], RequestDispatchReceipt] = field(
        default_factory=dict
    )
    runs: dict[UUID, Run] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    artifacts: list[TaskArtifact] = field(default_factory=list)
    workflow_definitions: dict[tuple[str, int], WorkflowDefinition] = field(default_factory=dict)
    workflow_executions: dict[UUID, WorkflowExecution] = field(default_factory=dict)
    project_workflow_bindings: dict[UUID, ProjectWorkflowBinding] = field(default_factory=dict)
    skills: dict[tuple[str, int], SkillDefinition] = field(default_factory=dict)
    phase_packs: dict[tuple[str, int], PhasePackDefinition] = field(default_factory=dict)
    model_profiles: dict[tuple[str, int], ModelProfile] = field(default_factory=dict)
    budget_accounts: dict[UUID, BudgetAccount] = field(default_factory=dict)
    budget_reservations: dict[str, BudgetReservation] = field(default_factory=dict)
    usage_records: list[UsageRecord] = field(default_factory=list)
    external_executions: dict[str, ExternalExecution] = field(default_factory=dict)
    workspace_operations: dict[UUID, WorkspaceOperation] = field(default_factory=dict)
    scm_publications: dict[UUID, ScmPublication] = field(default_factory=dict)
    service_accounts: dict[UUID, ServiceAccount] = field(default_factory=dict)


class MemoryProjectRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, project: Project) -> None:
        self._store.projects[project.id] = project

    async def get(self, project_id: UUID) -> Project | None:
        return self._store.projects.get(project_id)

    async def get_by_key(self, key: str) -> Project | None:
        return next(
            (project for project in self._store.projects.values() if project.key == key), None
        )

    async def list(self, *, status: ProjectStatus | None = None, limit: int = 100) -> list[Project]:
        matches = [
            project
            for project in self._store.projects.values()
            if status is None or project.status is status
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]


class MemoryServiceAccountRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, account: ServiceAccount) -> None:
        self._store.service_accounts[account.id] = account

    async def get(self, account_id: UUID) -> ServiceAccount | None:
        return self._store.service_accounts.get(account_id)

    async def get_by_key(self, key: str) -> ServiceAccount | None:
        return next(
            (account for account in self._store.service_accounts.values() if account.key == key),
            None,
        )

    async def disable(self, account_id: UUID) -> None:
        account = self._store.service_accounts.get(account_id)
        if account is not None:
            self._store.service_accounts[account_id] = replace(account, enabled=False)


class MemoryUserRequestRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request

    async def get(self, request_id: UUID) -> UserRequest | None:
        return self._store.requests.get(request_id)

    async def get_for_update(self, request_id: UUID) -> UserRequest | None:
        return self._store.requests.get(request_id)

    async def save(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: RequestStatus | None = None,
        limit: int = 100,
    ) -> list[UserRequest]:
        matches = [
            request
            for request in self._store.requests.values()
            if request.project_id == project_id and (status is None or request.status is status)
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]


class MemoryRunRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, run: Run) -> None:
        self._store.runs[run.id] = run

    async def get(self, run_id: UUID) -> Run | None:
        return self._store.runs.get(run_id)

    async def get_for_update(self, run_id: UUID) -> Run | None:
        return self._store.runs.get(run_id)

    async def save(self, run: Run) -> None:
        self._store.runs[run.id] = run

    async def list_by_request(
        self,
        request_id: UUID,
        *,
        status: RunStatus | None = None,
        limit: int = 100,
    ) -> list[Run]:
        matches = [
            run
            for run in self._store.runs.values()
            if run.request_id == request_id and (status is None or run.status is status)
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]


class MemoryRequestDispatchReceiptRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def try_claim(self, receipt: RequestDispatchReceipt) -> bool:
        key = (receipt.project_id, receipt.ingress_key, receipt.idempotency_key)
        if key in self._store.request_dispatch_receipts:
            return False
        self._store.request_dispatch_receipts[key] = receipt
        return True

    async def get(
        self,
        project_id: UUID,
        ingress_key: str,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> RequestDispatchReceipt | None:
        return self._store.request_dispatch_receipts.get((project_id, ingress_key, idempotency_key))

    async def save(self, receipt: RequestDispatchReceipt) -> None:
        self._store.request_dispatch_receipts[
            (receipt.project_id, receipt.ingress_key, receipt.idempotency_key)
        ] = receipt


class MemoryExternalExecutionRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, execution: ExternalExecution) -> None:
        self._store.external_executions[execution.idempotency_key] = execution

    async def get_by_idempotency_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> ExternalExecution | None:
        return self._store.external_executions.get(idempotency_key)

    async def get(self, execution_id: UUID) -> ExternalExecution | None:
        return next(
            (
                execution
                for execution in self._store.external_executions.values()
                if execution.id == execution_id
            ),
            None,
        )

    async def list(
        self,
        *,
        workflow_execution_id: UUID | None = None,
        run_id: UUID | None = None,
        status: ExternalExecutionStatus | None = None,
        limit: int = 100,
    ) -> list[ExternalExecution]:
        matches = [
            execution
            for execution in self._store.external_executions.values()
            if (workflow_execution_id is None or execution.execution_id == workflow_execution_id)
            and (run_id is None or execution.run_id == run_id)
            and (status is None or execution.status == status)
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]

    async def save(self, execution: ExternalExecution) -> None:
        self._store.external_executions[execution.idempotency_key] = execution


class MemoryWorkspaceOperationRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def try_add(self, operation: WorkspaceOperation) -> bool:
        if await self.get_by_idempotency_key(
            operation.external_execution_id, operation.idempotency_key
        ):
            return False
        self._store.workspace_operations[operation.id] = operation
        return True

    async def get(
        self, operation_id: UUID, *, for_update: bool = False
    ) -> WorkspaceOperation | None:
        return self._store.workspace_operations.get(operation_id)

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> WorkspaceOperation | None:
        return next(
            (
                operation
                for operation in self._store.workspace_operations.values()
                if operation.external_execution_id == external_execution_id
                and operation.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[WorkspaceOperation]:
        matches = [
            operation
            for operation in self._store.workspace_operations.values()
            if operation.external_execution_id == external_execution_id
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]

    async def claim_next(
        self, *, worker_id: str, workspace_scope: str, lease_seconds: int
    ) -> WorkspaceOperation | None:
        now = datetime.now().astimezone()
        candidates = [
            operation
            for operation in self._store.workspace_operations.values()
            if operation.workspace_scope == workspace_scope
            and (
                operation.status is WorkspaceOperationStatus.PENDING
                or (
                    operation.status is WorkspaceOperationStatus.CLAIMED
                    and operation.lease_expires_at is not None
                    and operation.lease_expires_at <= now
                )
            )
        ]
        if not candidates:
            return None
        operation = min(candidates, key=lambda value: (value.created_at, value.id))
        operation.claim(worker_id, lease_seconds=lease_seconds, at=now)
        return operation

    async def save(self, operation: WorkspaceOperation) -> None:
        self._store.workspace_operations[operation.id] = operation


class MemoryScmPublicationRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def try_add(self, publication: ScmPublication) -> bool:
        if await self.get_by_idempotency_key(
            publication.external_execution_id, publication.idempotency_key
        ):
            return False
        self._store.scm_publications[publication.id] = publication
        return True

    async def get(self, publication_id: UUID, *, for_update: bool = False) -> ScmPublication | None:
        return self._store.scm_publications.get(publication_id)

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> ScmPublication | None:
        return next(
            (
                publication
                for publication in self._store.scm_publications.values()
                if publication.external_execution_id == external_execution_id
                and publication.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[ScmPublication]:
        matches = [
            publication
            for publication in self._store.scm_publications.values()
            if publication.external_execution_id == external_execution_id
        ]
        return sorted(matches, key=lambda value: (value.created_at, value.id), reverse=True)[:limit]

    async def claim_next(
        self, *, worker_id: str, provider_key: str, workspace_scope: str, lease_seconds: int
    ) -> ScmPublication | None:
        now = datetime.now().astimezone()
        candidates = [
            publication
            for publication in self._store.scm_publications.values()
            if publication.provider_key == provider_key
            and publication.workspace_scope == workspace_scope
            and (
                publication.status is ScmPublicationStatus.PENDING
                or (
                    publication.status is ScmPublicationStatus.CLAIMED
                    and publication.lease_expires_at is not None
                    and publication.lease_expires_at <= now
                )
            )
        ]
        if not candidates:
            return None
        publication = min(candidates, key=lambda value: (value.created_at, value.id))
        publication.claim(worker_id, lease_seconds=lease_seconds, at=now)
        return publication

    async def save(self, publication: ScmPublication) -> None:
        self._store.scm_publications[publication.id] = publication


class MemoryEventRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def append(self, event: DomainEvent) -> None:
        self._store.events.append(replace(event, sequence=len(self._store.events) + 1))

    async def get(self, event_id: UUID) -> DomainEvent | None:
        return next((event for event in self._store.events if event.id == event_id), None)

    async def list_after(
        self,
        *,
        aggregate_type: str,
        after: DomainEvent | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        after_sequence = after.sequence if after is not None else 0
        if after_sequence is None:
            raise ValueError("persisted event cursor requires a sequence")
        return [
            event
            for event in self._store.events
            if event.aggregate_type == aggregate_type
            and event.sequence is not None
            and event.sequence > after_sequence
        ][:limit]

    async def list_project_after(
        self,
        *,
        project_id: UUID,
        after: DomainEvent | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        after_sequence = after.sequence if after is not None else 0
        if after_sequence is None:
            raise ValueError("persisted event cursor requires a sequence")

        request_ids = {
            request.id
            for request in self._store.requests.values()
            if request.project_id == project_id
        }
        run_ids = {run.id for run in self._store.runs.values() if run.request_id in request_ids}
        workflow_ids = {
            execution.id
            for execution in self._store.workflow_executions.values()
            if execution.snapshot.run_id in run_ids
        }
        external_ids = {
            execution.id
            for execution in self._store.external_executions.values()
            if execution.run_id in run_ids
        }
        workspace_operation_ids = {
            operation.id
            for operation in self._store.workspace_operations.values()
            if operation.external_execution_id in external_ids
        }
        scm_publication_ids = {
            publication.id
            for publication in self._store.scm_publications.values()
            if publication.external_execution_id in external_ids
        }
        budget_account_ids = {
            account.id
            for account in self._store.budget_accounts.values()
            if account.project_id == project_id
        }
        budget_reservation_ids = {
            reservation.id
            for reservation in self._store.budget_reservations.values()
            if reservation.project_id == project_id
        }
        aggregate_ids = {
            "project": {project_id},
            "request": request_ids,
            "run": run_ids,
            "workflow_execution": workflow_ids,
            "external_execution": external_ids,
            "workspace_operation": workspace_operation_ids,
            "scm_publication": scm_publication_ids,
            "budget_account": budget_account_ids,
            "budget_reservation": budget_reservation_ids,
        }
        return [
            event
            for event in self._store.events
            if event.sequence is not None
            and event.sequence > after_sequence
            and event.aggregate_id in aggregate_ids.get(event.aggregate_type, set())
        ][:limit]


class MemoryTaskArtifactRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, artifact: TaskArtifact) -> None:
        self._store.artifacts.append(artifact)

    async def list_for_execution(self, execution_id: UUID) -> list[TaskArtifact]:
        return [
            artifact for artifact in self._store.artifacts if artifact.execution_id == execution_id
        ]

    async def list_latest_for_nodes(
        self, execution_id: UUID, node_keys: Collection[str]
    ) -> list[TaskArtifact]:
        latest: dict[str, TaskArtifact] = {}
        for artifact in self._store.artifacts:
            if artifact.execution_id != execution_id or artifact.producer_node_key not in node_keys:
                continue
            current = latest.get(artifact.producer_node_key)
            if current is None or artifact.visit_count > current.visit_count:
                latest[artifact.producer_node_key] = artifact
        return [latest[key] for key in sorted(latest)]


class MemorySkillRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, skill: SkillDefinition) -> None:
        self._store.skills[(skill.key, skill.version)] = skill

    async def get(self, key: str, version: int | None = None) -> SkillDefinition | None:
        if version is not None:
            return self._store.skills.get((key, version))
        matches = [
            skill for (stored_key, _), skill in self._store.skills.items() if stored_key == key
        ]
        return max(matches, key=lambda skill: skill.version, default=None)

    async def list_latest(self) -> list[SkillDefinition]:
        keys = sorted({key for key, _ in self._store.skills})
        return [
            max(
                (
                    skill
                    for (stored_key, _), skill in self._store.skills.items()
                    if stored_key == key
                ),
                key=lambda skill: skill.version,
            )
            for key in keys
        ]


class MemoryPhasePackRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, phase_pack: PhasePackDefinition) -> None:
        self._store.phase_packs[(phase_pack.key, phase_pack.version)] = phase_pack

    async def get(self, key: str, version: int | None = None) -> PhasePackDefinition | None:
        if version is not None:
            return self._store.phase_packs.get((key, version))
        matches = [
            value for (stored_key, _), value in self._store.phase_packs.items() if stored_key == key
        ]
        return max(matches, key=lambda value: value.version, default=None)

    async def list_latest(self) -> list[PhasePackDefinition]:
        keys = sorted({key for key, _ in self._store.phase_packs})
        return [
            max(
                (
                    value
                    for (stored_key, _), value in self._store.phase_packs.items()
                    if stored_key == key
                ),
                key=lambda value: value.version,
            )
            for key in keys
        ]


class MemoryModelProfileRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, profile: ModelProfile) -> None:
        self._store.model_profiles[(profile.key, profile.version)] = profile

    async def get(self, key: str, version: int | None = None) -> ModelProfile | None:
        if version is not None:
            return self._store.model_profiles.get((key, version))
        matches = [
            profile
            for (stored_key, _), profile in self._store.model_profiles.items()
            if stored_key == key
        ]
        return max(matches, key=lambda profile: profile.version, default=None)

    async def list_latest(self) -> list[ModelProfile]:
        keys = sorted({key for key, _ in self._store.model_profiles})
        return [
            max(
                (
                    profile
                    for (stored_key, _), profile in self._store.model_profiles.items()
                    if stored_key == key
                ),
                key=lambda profile: profile.version,
            )
            for key in keys
        ]


class MemoryBudgetAccountRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, account: BudgetAccount) -> None:
        self._store.budget_accounts[account.project_id] = account

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> BudgetAccount | None:
        return self._store.budget_accounts.get(project_id)

    async def save(self, account: BudgetAccount) -> None:
        self._store.budget_accounts[account.project_id] = account


class MemoryBudgetReservationRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, reservation: BudgetReservation) -> None:
        self._store.budget_reservations[reservation.idempotency_key] = reservation

    async def get_by_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> BudgetReservation | None:
        return self._store.budget_reservations.get(idempotency_key)

    async def list_reserved_by_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> list[BudgetReservation]:
        return [
            reservation
            for reservation in self._store.budget_reservations.values()
            if reservation.run_id == run_id
            and reservation.status is BudgetReservationStatus.RESERVED
        ]

    async def save(self, reservation: BudgetReservation) -> None:
        self._store.budget_reservations[reservation.idempotency_key] = reservation


class MemoryUsageRecordRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, record: UsageRecord) -> None:
        self._store.usage_records.append(record)

    async def get_by_reservation(self, reservation_id: UUID) -> UsageRecord | None:
        return next(
            (
                record
                for record in self._store.usage_records
                if record.reservation_id == reservation_id
            ),
            None,
        )

    async def list_by_project(self, project_id: UUID) -> list[UsageRecord]:
        return [record for record in self._store.usage_records if record.project_id == project_id]


class MemoryWorkflowDefinitionRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, definition: WorkflowDefinition) -> None:
        self._store.workflow_definitions[(definition.key, definition.version)] = definition

    async def get(self, key: str, version: int | None = None) -> WorkflowDefinition | None:
        if version is not None:
            return self._store.workflow_definitions.get((key, version))
        matches = [
            definition
            for (stored_key, _), definition in self._store.workflow_definitions.items()
            if stored_key == key
        ]
        return max(matches, key=lambda definition: definition.version, default=None)

    async def list_latest(self) -> list[WorkflowDefinition]:
        keys = sorted({key for key, _ in self._store.workflow_definitions})
        return [
            max(
                (
                    definition
                    for (stored_key, _), definition in self._store.workflow_definitions.items()
                    if stored_key == key
                ),
                key=lambda definition: definition.version,
            )
            for key in keys
        ]


class MemoryProjectWorkflowBindingRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> ProjectWorkflowBinding | None:
        return self._store.project_workflow_bindings.get(project_id)

    async def save(self, binding: ProjectWorkflowBinding) -> None:
        self._store.project_workflow_bindings[binding.project_id] = binding


class MemoryWorkflowExecutionRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, execution: WorkflowExecution) -> None:
        self._store.workflow_executions[execution.id] = execution

    async def get(self, execution_id: UUID) -> WorkflowExecution | None:
        return self._store.workflow_executions.get(execution_id)

    async def get_for_update(self, execution_id: UUID) -> WorkflowExecution | None:
        return self._store.workflow_executions.get(execution_id)

    async def get_by_run(self, run_id: UUID) -> WorkflowExecution | None:
        return next(
            (
                execution
                for execution in self._store.workflow_executions.values()
                if execution.snapshot.run_id == run_id
            ),
            None,
        )

    async def get_by_run_for_update(self, run_id: UUID) -> WorkflowExecution | None:
        return await self.get_by_run(run_id)

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: WorkflowStatus | None = None,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        request_ids = {
            request.id
            for request in self._store.requests.values()
            if request.project_id == project_id
        }
        run_ids = {run.id for run in self._store.runs.values() if run.request_id in request_ids}
        matches = [
            execution
            for execution in self._store.workflow_executions.values()
            if execution.snapshot.run_id in run_ids
            and (status is None or execution.status is status)
        ]
        return sorted(matches, key=lambda value: (value.updated_at, value.id), reverse=True)[:limit]

    async def get_ready_for_update(
        self, executor_keys: Collection[str] | None = None
    ) -> WorkflowTaskCandidate | None:
        candidates = [
            (execution, node)
            for execution in self._store.workflow_executions.values()
            if execution.status is WorkflowStatus.RUNNING
            for node in execution.nodes.values()
            if node.status is NodeExecutionStatus.READY
            and (executor_keys is None or node.executor_key in executor_keys)
        ]
        if not candidates:
            return None
        execution, node = min(candidates, key=lambda item: (item[1].updated_at, item[1].id))
        return WorkflowTaskCandidate(execution=execution, node_key=node.node_key)

    async def get_expired_for_update(self, at: datetime) -> WorkflowTaskCandidate | None:
        candidates = [
            (execution, node)
            for execution in self._store.workflow_executions.values()
            if execution.status is WorkflowStatus.RUNNING
            for node in execution.nodes.values()
            if node.status is NodeExecutionStatus.RUNNING
            and node.lease_expires_at is not None
            and node.lease_expires_at <= at
        ]
        if not candidates:
            return None
        execution, node = min(
            candidates,
            key=lambda item: (item[1].lease_expires_at or at, item[1].id),
        )
        return WorkflowTaskCandidate(execution=execution, node_key=node.node_key)

    async def save(self, execution: WorkflowExecution) -> None:
        self._store.workflow_executions[execution.id] = execution


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore) -> None:
        self.projects = MemoryProjectRepository(store)
        self.requests = MemoryUserRequestRepository(store)
        self.request_dispatch_receipts = MemoryRequestDispatchReceiptRepository(store)
        self.runs = MemoryRunRepository(store)
        self.events = MemoryEventRepository(store)
        self.artifacts = MemoryTaskArtifactRepository(store)
        self.skills = MemorySkillRepository(store)
        self.phase_packs = MemoryPhasePackRepository(store)
        self.model_profiles = MemoryModelProfileRepository(store)
        self.budget_accounts = MemoryBudgetAccountRepository(store)
        self.budget_reservations = MemoryBudgetReservationRepository(store)
        self.usage_records = MemoryUsageRecordRepository(store)
        self.external_executions = MemoryExternalExecutionRepository(store)
        self.workspace_operations = MemoryWorkspaceOperationRepository(store)
        self.scm_publications = MemoryScmPublicationRepository(store)
        self.workflow_definitions = MemoryWorkflowDefinitionRepository(store)
        self.workflow_executions = MemoryWorkflowExecutionRepository(store)
        self.project_workflow_bindings = MemoryProjectWorkflowBindingRepository(store)
        self.service_accounts = MemoryServiceAccountRepository(store)
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True
