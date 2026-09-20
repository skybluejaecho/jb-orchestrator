"""Persistence port for external execution mappings."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.external_executions.models import ExternalExecution, ExternalExecutionStatus


class ExternalExecutionRepository(Protocol):
    async def add(self, execution: ExternalExecution) -> None: ...

    async def get_by_idempotency_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> ExternalExecution | None: ...

    async def get(self, execution_id: UUID) -> ExternalExecution | None: ...

    async def list(
        self,
        *,
        workflow_execution_id: UUID | None = None,
        run_id: UUID | None = None,
        status: ExternalExecutionStatus | None = None,
        limit: int = 100,
    ) -> list[ExternalExecution]: ...

    async def save(self, execution: ExternalExecution) -> None: ...
