"""Persistence port for external execution mappings."""

from typing import Protocol

from jb_orchestrator.external_executions.models import ExternalExecution


class ExternalExecutionRepository(Protocol):
    async def add(self, execution: ExternalExecution) -> None: ...

    async def get_by_idempotency_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> ExternalExecution | None: ...

    async def save(self, execution: ExternalExecution) -> None: ...
