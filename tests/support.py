"""In-memory application adapters used by tests."""

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from jb_orchestrator.budgets import (
    BudgetAccount,
    BudgetReservation,
    BudgetReservationStatus,
    UsageRecord,
)
from jb_orchestrator.domain import DomainEvent, Project, Run, UserRequest
from jb_orchestrator.external_executions import ExternalExecution, ExternalExecutionStatus
from jb_orchestrator.model_routing import ModelProfile
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import (
    NodeExecutionStatus,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowTaskCandidate,
)


@dataclass
class MemoryStore:
    projects: dict[UUID, Project] = field(default_factory=dict)
    requests: dict[UUID, UserRequest] = field(default_factory=dict)
    runs: dict[UUID, Run] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    workflow_definitions: dict[tuple[str, int], WorkflowDefinition] = field(default_factory=dict)
    workflow_executions: dict[UUID, WorkflowExecution] = field(default_factory=dict)
    skills: dict[tuple[str, int], SkillDefinition] = field(default_factory=dict)
    model_profiles: dict[tuple[str, int], ModelProfile] = field(default_factory=dict)
    budget_accounts: dict[UUID, BudgetAccount] = field(default_factory=dict)
    budget_reservations: dict[str, BudgetReservation] = field(default_factory=dict)
    usage_records: list[UsageRecord] = field(default_factory=list)
    external_executions: dict[str, ExternalExecution] = field(default_factory=dict)


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


class MemoryUserRequestRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request

    async def get(self, request_id: UUID) -> UserRequest | None:
        return self._store.requests.get(request_id)

    async def save(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request


class MemoryRunRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, run: Run) -> None:
        self._store.runs[run.id] = run

    async def get(self, run_id: UUID) -> Run | None:
        return self._store.runs.get(run_id)

    async def save(self, run: Run) -> None:
        self._store.runs[run.id] = run


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


class MemoryWorkflowExecutionRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, execution: WorkflowExecution) -> None:
        self._store.workflow_executions[execution.id] = execution

    async def get(self, execution_id: UUID) -> WorkflowExecution | None:
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
        self.runs = MemoryRunRepository(store)
        self.events = MemoryEventRepository(store)
        self.skills = MemorySkillRepository(store)
        self.model_profiles = MemoryModelProfileRepository(store)
        self.budget_accounts = MemoryBudgetAccountRepository(store)
        self.budget_reservations = MemoryBudgetReservationRepository(store)
        self.usage_records = MemoryUsageRecordRepository(store)
        self.external_executions = MemoryExternalExecutionRepository(store)
        self.workflow_definitions = MemoryWorkflowDefinitionRepository(store)
        self.workflow_executions = MemoryWorkflowExecutionRepository(store)
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
