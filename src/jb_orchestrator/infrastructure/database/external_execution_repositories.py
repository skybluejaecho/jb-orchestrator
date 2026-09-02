"""SQLAlchemy adapter for external execution mappings."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.external_executions import ExternalExecution
from jb_orchestrator.infrastructure.database.models import ExternalExecutionRecord


def external_execution_from_record(record: ExternalExecutionRecord) -> ExternalExecution:
    return ExternalExecution(
        id=record.id,
        execution_id=record.execution_id,
        run_id=record.run_id,
        node_key=record.node_key,
        executor_key=record.executor_key,
        idempotency_key=record.idempotency_key,
        external_session_key=record.external_session_key,
        external_agent_id=record.external_agent_id,
        external_run_id=record.external_run_id,
        status=record.status,
        terminal_result=record.terminal_result,
        failure_reason=record.failure_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class SqlAlchemyExternalExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, execution: ExternalExecution) -> None:
        self._session.add(
            ExternalExecutionRecord(
                id=execution.id,
                execution_id=execution.execution_id,
                run_id=execution.run_id,
                node_key=execution.node_key,
                executor_key=execution.executor_key,
                idempotency_key=execution.idempotency_key,
                external_session_key=execution.external_session_key,
                external_agent_id=execution.external_agent_id,
                external_run_id=execution.external_run_id,
                status=execution.status,
                terminal_result=execution.terminal_result,
                failure_reason=execution.failure_reason,
                created_at=execution.created_at,
                updated_at=execution.updated_at,
                completed_at=execution.completed_at,
            )
        )

    async def get_by_idempotency_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> ExternalExecution | None:
        statement = select(ExternalExecutionRecord).where(
            ExternalExecutionRecord.idempotency_key == idempotency_key
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return external_execution_from_record(record) if record is not None else None

    async def save(self, execution: ExternalExecution) -> None:
        record = await self._session.get(ExternalExecutionRecord, execution.id)
        if record is None:
            raise LookupError(f"external execution not found: {execution.id}")
        record.external_run_id = execution.external_run_id
        record.status = execution.status
        record.terminal_result = execution.terminal_result
        record.failure_reason = execution.failure_reason
        record.updated_at = execution.updated_at
        record.completed_at = execution.completed_at
