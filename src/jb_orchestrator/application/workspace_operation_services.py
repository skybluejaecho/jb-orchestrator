"""Application service for durable workspace maintenance commands."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent, DomainValidationError
from jb_orchestrator.external_executions import ExternalExecution
from jb_orchestrator.workspace_operations import WorkspaceOperation, WorkspaceOperationKind


class WorkspaceOperationService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def request(
        self,
        external_execution_id: UUID,
        *,
        kind: WorkspaceOperationKind,
        target_ref: str,
        idempotency_key: str,
        requested_by: str,
        confirmation: str | None = None,
    ) -> tuple[WorkspaceOperation, bool]:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise DomainValidationError("workspace operation idempotency key must not be empty")
        if kind is WorkspaceOperationKind.CLEANUP and confirmation != str(external_execution_id):
            raise DomainValidationError(
                "cleanup confirmation must equal the external execution UUID"
            )
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._execution(unit_of_work, external_execution_id)
            if not execution.workspace_path or not execution.workspace_scope:
                raise ResourceConflict("external execution has no managed workspace scope")
            if kind is WorkspaceOperationKind.CLEANUP and not execution.is_terminal:
                raise ResourceConflict("workspace cleanup requires a terminal external execution")
            existing = await unit_of_work.workspace_operations.get_by_idempotency_key(
                external_execution_id, normalized_key
            )
            if existing is not None:
                if existing.kind is not kind or existing.target_ref != target_ref.strip():
                    raise ResourceConflict("idempotency key was already used for another command")
                return existing, True
            operation = WorkspaceOperation(
                external_execution_id=external_execution_id,
                kind=kind,
                target_ref=target_ref,
                workspace_scope=execution.workspace_scope,
                idempotency_key=normalized_key,
                requested_by=requested_by,
            )
            if not await unit_of_work.workspace_operations.try_add(operation):
                existing = await unit_of_work.workspace_operations.get_by_idempotency_key(
                    external_execution_id, normalized_key
                )
                if existing is None:  # pragma: no cover - database invariant
                    raise RuntimeError("workspace operation idempotency claim disappeared")
                if existing.kind is not kind or existing.target_ref != target_ref.strip():
                    raise ResourceConflict("idempotency key was already used for another command")
                return existing, True
            await self._event(unit_of_work, operation, execution, "workspace_operation.requested")
            await unit_of_work.commit()
            return operation, False

    async def list_for_execution(self, external_execution_id: UUID) -> list[WorkspaceOperation]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._execution(unit_of_work, external_execution_id)
            return await unit_of_work.workspace_operations.list_for_execution(external_execution_id)

    async def claim_next(
        self, *, worker_id: str, workspace_scope: str, lease_seconds: int = 300
    ) -> WorkspaceOperation | None:
        async with self._unit_of_work_factory() as unit_of_work:
            operation = await unit_of_work.workspace_operations.claim_next(
                worker_id=worker_id,
                workspace_scope=workspace_scope,
                lease_seconds=lease_seconds,
            )
            if operation is None:
                return None
            execution = await self._execution(unit_of_work, operation.external_execution_id)
            await self._event(unit_of_work, operation, execution, "workspace_operation.claimed")
            await unit_of_work.commit()
            return operation

    async def succeed(
        self, operation_id: UUID, lease_token: UUID, result: dict[str, Any]
    ) -> WorkspaceOperation:
        return await self._finish(operation_id, lease_token, result=result)

    async def fail(self, operation_id: UUID, lease_token: UUID, reason: str) -> WorkspaceOperation:
        return await self._finish(operation_id, lease_token, failure_reason=reason)

    async def _finish(
        self,
        operation_id: UUID,
        lease_token: UUID,
        *,
        result: dict[str, Any] | None = None,
        failure_reason: str | None = None,
    ) -> WorkspaceOperation:
        async with self._unit_of_work_factory() as unit_of_work:
            operation = await unit_of_work.workspace_operations.get(operation_id, for_update=True)
            if operation is None:
                raise ResourceNotFound(f"workspace operation not found: {operation_id}")
            if failure_reason is None:
                operation.succeed(lease_token, result or {})
                event_type = "workspace_operation.succeeded"
            else:
                operation.fail(lease_token, failure_reason)
                event_type = "workspace_operation.failed"
            await unit_of_work.workspace_operations.save(operation)
            execution = await self._execution(unit_of_work, operation.external_execution_id)
            await self._event(unit_of_work, operation, execution, event_type)
            await unit_of_work.commit()
            return operation

    @staticmethod
    async def _execution(unit_of_work: UnitOfWork, execution_id: UUID) -> ExternalExecution:
        execution = await unit_of_work.external_executions.get(execution_id)
        if execution is None:
            raise ResourceNotFound(f"external execution not found: {execution_id}")
        return execution

    @staticmethod
    async def _event(
        unit_of_work: UnitOfWork,
        operation: WorkspaceOperation,
        execution: ExternalExecution,
        event_type: str,
    ) -> None:
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="workspace_operation",
                aggregate_id=operation.id,
                event_type=event_type,
                payload={
                    "external_execution_id": str(execution.id),
                    "workflow_execution_id": str(execution.execution_id),
                    "run_id": str(execution.run_id),
                    "kind": operation.kind.value,
                    "target_ref": operation.target_ref,
                    "status": operation.status.value,
                    "worker_id": operation.worker_id,
                    "failure_reason": operation.failure_reason,
                },
            )
        )
