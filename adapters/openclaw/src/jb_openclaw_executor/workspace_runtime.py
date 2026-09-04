"""Worker for durable OpenClaw workspace maintenance commands."""

import asyncio
from dataclasses import asdict
from typing import Any

from jb_openclaw_executor.workspace import OpenClawWorkspaceError, OpenClawWorkspaceManager
from jb_orchestrator.application import ExternalExecutionService, WorkspaceOperationService
from jb_orchestrator.workspace_operations import WorkspaceOperationKind


class WorkspaceOperationRuntime:
    def __init__(
        self,
        worker_id: str,
        operations: WorkspaceOperationService,
        executions: ExternalExecutionService,
        manager: OpenClawWorkspaceManager,
        *,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 300,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("workspace worker id must not be empty")
        if manager.scope is None:
            raise OpenClawWorkspaceError("workspace worker requires JB_OPENCLAW_WORKSPACE_ROOT")
        if poll_interval_seconds <= 0 or lease_seconds <= 0:
            raise ValueError("workspace worker intervals must be positive")
        self._worker_id = worker_id.strip()
        self._operations = operations
        self._executions = executions
        self._manager = manager
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds

    async def run_once(self) -> bool:
        scope = self._manager.scope
        if scope is None:  # pragma: no cover - constructor guard
            raise RuntimeError("workspace manager scope disappeared")
        operation = await self._operations.claim_next(
            worker_id=self._worker_id,
            workspace_scope=scope,
            lease_seconds=self._lease_seconds,
        )
        if operation is None:
            return False
        lease_token = operation.lease_token
        if lease_token is None:  # pragma: no cover - repository contract
            raise RuntimeError("claimed workspace operation has no lease token")
        try:
            result: dict[str, Any]
            execution = await self._executions.get_by_id(operation.external_execution_id)
            if operation.kind is WorkspaceOperationKind.INSPECT:
                if execution.workspace_released_at is not None:
                    result = {
                        "status": "already_released",
                        "released_at": execution.workspace_released_at.isoformat(),
                    }
                else:
                    review = await self._manager.review(execution, merged_into=operation.target_ref)
                    result = {"status": "reviewed", **asdict(review)}
            else:
                if execution.workspace_released_at is not None:
                    result = {
                        "status": "already_released",
                        "released_at": execution.workspace_released_at.isoformat(),
                    }
                else:
                    review = await self._manager.cleanup(
                        execution, merged_into=operation.target_ref
                    )
                    released = await self._executions.release_workspace(execution.id)
                    result = {
                        "status": "released",
                        **asdict(review),
                        "released_at": (
                            released.workspace_released_at.isoformat()
                            if released.workspace_released_at is not None
                            else None
                        ),
                    }
        except Exception as exc:
            await self._operations.fail(operation.id, lease_token, str(exc) or type(exc).__name__)
        else:
            await self._operations.succeed(operation.id, lease_token, result)
        return True

    async def run(self) -> None:
        while True:
            if not await self.run_once():
                await asyncio.sleep(self._poll_interval_seconds)
