"""Transactional lifecycle service for external runtime identifiers."""

from collections.abc import Callable
from typing import Any

from jb_orchestrator.application.unit_of_work import UnitOfWork
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
            )
            await unit_of_work.external_executions.add(execution)
            await unit_of_work.commit()
            return execution

    async def accept(self, idempotency_key: str, external_run_id: str) -> ExternalExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._required(unit_of_work, idempotency_key)
            execution.accept(external_run_id)
            await unit_of_work.external_executions.save(execution)
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
            execution.finish(
                status,
                terminal_result=terminal_result,
                failure_reason=failure_reason,
            )
            await unit_of_work.external_executions.save(execution)
            await unit_of_work.commit()
            return execution

    async def get(self, idempotency_key: str) -> ExternalExecution | None:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.external_executions.get_by_idempotency_key(idempotency_key)

    @staticmethod
    async def _required(unit_of_work: UnitOfWork, key: str) -> ExternalExecution:
        execution = await unit_of_work.external_executions.get_by_idempotency_key(
            key, for_update=True
        )
        if execution is None:
            raise LookupError(f"external execution not found: {key}")
        return execution
