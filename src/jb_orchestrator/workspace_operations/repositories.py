"""Persistence port for workspace operation commands."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.workspace_operations.models import WorkspaceOperation


class WorkspaceOperationRepository(Protocol):
    async def try_add(self, operation: WorkspaceOperation) -> bool: ...

    async def get(
        self, operation_id: UUID, *, for_update: bool = False
    ) -> WorkspaceOperation | None: ...

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> WorkspaceOperation | None: ...

    async def list_for_execution(self, external_execution_id: UUID) -> list[WorkspaceOperation]: ...

    async def claim_next(
        self, *, worker_id: str, workspace_scope: str, lease_seconds: int
    ) -> WorkspaceOperation | None: ...

    async def save(self, operation: WorkspaceOperation) -> None: ...
