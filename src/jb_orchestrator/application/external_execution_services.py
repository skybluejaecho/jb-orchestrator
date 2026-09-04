"""Transactional lifecycle service for external runtime identifiers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.external_executions import ExternalExecution, ExternalExecutionStatus
from jb_orchestrator.worker.models import TaskClaim


class ExternalExecutionService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def prepare(
        self,
        claim: TaskClaim,
        *,
        session_key: str,
        agent_id: str | None,
        workspace_path: str | None = None,
        workspace_repository_path: str | None = None,
        workspace_branch: str | None = None,
        workspace_base_ref: str | None = None,
    ) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.external_executions.get_by_idempotency_key(
                claim.idempotency_key, for_update=True
            )
            if existing is not None:
                return existing
            execution = ExternalExecution(
                execution_id=claim.execution_id,
                run_id=claim.run_id,
                node_key=claim.node_key,
                executor_key=claim.executor_key,
                idempotency_key=claim.idempotency_key,
                external_session_key=session_key,
                external_agent_id=agent_id,
                workspace_path=workspace_path,
                workspace_repository_path=workspace_repository_path,
                workspace_branch=workspace_branch,
                workspace_base_ref=workspace_base_ref,
            )
            await unit_of_work.external_executions.add(execution)
            await self._append_event(unit_of_work, execution, "external_execution.prepared")
            await unit_of_work.commit()
            return execution

    async def accept(self, idempotency_key: str, external_run_id: str) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._required(unit_of_work, idempotency_key)
            if (
                execution.status is ExternalExecutionStatus.ACTIVE
                and execution.external_run_id == external_run_id.strip()
            ):
                return execution
            execution.accept(external_run_id)
            await unit_of_work.external_executions.save(execution)
            await self._append_event(unit_of_work, execution, "external_execution.accepted")
            await unit_of_work.commit()
            return execution

    async def finish(
        self,
        idempotency_key: str,
        status: ExternalExecutionStatus,
        *,
        terminal_result: dict[str, Any] | None = None,
        failure_reason: str | None = None,
    ) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._required(unit_of_work, idempotency_key)
            if execution.is_terminal and execution.status is status:
                return execution
            execution.finish(
                status,
                terminal_result=terminal_result,
                failure_reason=failure_reason,
            )
            await unit_of_work.external_executions.save(execution)
            await self._append_event(unit_of_work, execution, "external_execution.finished")
            await unit_of_work.commit()
            return execution

    async def get(self, idempotency_key: str) -> ExternalExecution | None:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.external_executions.get_by_idempotency_key(idempotency_key)

    async def release_workspace(self, execution_id: UUID) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.external_executions.get(execution_id)
            if current is None:
                raise ResourceNotFound(f"external execution not found: {execution_id}")
            execution = await self._required(unit_of_work, current.idempotency_key)
            if execution.workspace_released_at is not None:
                return execution
            execution.release_workspace()
            await unit_of_work.external_executions.save(execution)
            await self._append_event(
                unit_of_work, execution, "external_execution.workspace_released"
            )
            await unit_of_work.commit()
            return execution

    async def get_by_id(self, execution_id: UUID) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await unit_of_work.external_executions.get(execution_id)
            if execution is None:
                raise ResourceNotFound(f"external execution not found: {execution_id}")
            return execution

    async def list(
        self,
        *,
        workflow_execution_id: UUID | None = None,
        run_id: UUID | None = None,
        status: ExternalExecutionStatus | None = None,
        limit: int = 100,
    ) -> list[ExternalExecution]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.external_executions.list(
                workflow_execution_id=workflow_execution_id,
                run_id=run_id,
                status=status,
                limit=limit,
            )

    async def list_events(
        self,
        *,
        after_event_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[DomainEvent]:
        async with self._unit_of_work_factory() as unit_of_work:
            after = None
            if after_event_id is not None:
                after = await unit_of_work.events.get(after_event_id)
                if after is None:
                    raise ResourceNotFound(f"event cursor not found: {after_event_id}")
            return await unit_of_work.events.list_after(
                aggregate_type="external_execution",
                after=after,
                limit=limit,
            )

    @staticmethod
    async def _required(unit_of_work: UnitOfWork, key: str) -> ExternalExecution:
        execution = await unit_of_work.external_executions.get_by_idempotency_key(
            key, for_update=True
        )
        if execution is None:
            raise LookupError(f"external execution not found: {key}")
        return execution

    @staticmethod
    async def _append_event(
        unit_of_work: UnitOfWork,
        execution: ExternalExecution,
        event_type: str,
    ) -> None:
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="external_execution",
                aggregate_id=execution.id,
                event_type=event_type,
                payload={
                    "workflow_execution_id": str(execution.execution_id),
                    "run_id": str(execution.run_id),
                    "node_key": execution.node_key,
                    "executor_key": execution.executor_key,
                    "status": execution.status.value,
                    "external_session_key": execution.external_session_key,
                    "external_run_id": execution.external_run_id,
                    "workspace_path": execution.workspace_path,
                    "workspace_repository_path": execution.workspace_repository_path,
                    "workspace_branch": execution.workspace_branch,
                    "workspace_base_ref": execution.workspace_base_ref,
                    "workspace_released_at": (
                        execution.workspace_released_at.isoformat()
                        if execution.workspace_released_at is not None
                        else None
                    ),
                },
            )
        )
