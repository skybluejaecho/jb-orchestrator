"""Persistence ports for workflow definitions and executions."""

from collections.abc import Collection
from datetime import datetime
from typing import Protocol
from uuid import UUID

from jb_orchestrator.workflows.models import (
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowTaskCandidate,
)


class WorkflowDefinitionRepository(Protocol):
    async def add(self, definition: WorkflowDefinition) -> None: ...

    async def get(self, key: str, version: int | None = None) -> WorkflowDefinition | None: ...

    async def list_latest(self) -> list[WorkflowDefinition]: ...


class WorkflowExecutionRepository(Protocol):
    async def add(self, execution: WorkflowExecution) -> None: ...

    async def get(self, execution_id: UUID) -> WorkflowExecution | None: ...

    async def get_for_update(self, execution_id: UUID) -> WorkflowExecution | None: ...

    async def get_by_run(self, run_id: UUID) -> WorkflowExecution | None: ...

    async def get_by_run_for_update(self, run_id: UUID) -> WorkflowExecution | None: ...

    async def get_ready_for_update(
        self, executor_keys: Collection[str] | None = None
    ) -> WorkflowTaskCandidate | None: ...

    async def get_expired_for_update(self, at: datetime) -> WorkflowTaskCandidate | None: ...

    async def save(self, execution: WorkflowExecution) -> None: ...
