"""In-memory application adapters used by tests."""

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from jb_orchestrator.domain import DomainEvent, Project, Run, UserRequest
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


class MemoryEventRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def append(self, event: DomainEvent) -> None:
        self._store.events.append(event)


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
