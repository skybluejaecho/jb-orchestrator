"""SQLAlchemy adapter for workspace operation commands."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import WorkspaceOperationRecord
from jb_orchestrator.workspace_operations import (
    WorkspaceOperation,
    WorkspaceOperationStatus,
)


def workspace_operation_from_record(record: WorkspaceOperationRecord) -> WorkspaceOperation:
    return WorkspaceOperation(
        id=record.id,
        external_execution_id=record.external_execution_id,
        kind=record.kind,
        target_ref=record.target_ref,
        workspace_scope=record.workspace_scope,
        idempotency_key=record.idempotency_key,
        requested_by=record.requested_by,
        status=record.status,
        worker_id=record.worker_id,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        result=record.result,
        failure_reason=record.failure_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class SqlAlchemyWorkspaceOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_add(self, operation: WorkspaceOperation) -> bool:
        dialect_name = self._session.get_bind().dialect.name
        values = self._values(operation)
        if dialect_name == "postgresql":
            inserted_id = await self._session.scalar(
                postgresql_insert(WorkspaceOperationRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["external_execution_id", "idempotency_key"])
                .returning(WorkspaceOperationRecord.id)
            )
        elif dialect_name == "sqlite":
            inserted_id = await self._session.scalar(
                sqlite_insert(WorkspaceOperationRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["external_execution_id", "idempotency_key"])
                .returning(WorkspaceOperationRecord.id)
            )
        else:
            raise RuntimeError(f"unsupported workspace operation database: {dialect_name}")
        return inserted_id is not None

    async def get(
        self, operation_id: UUID, *, for_update: bool = False
    ) -> WorkspaceOperation | None:
        statement = select(WorkspaceOperationRecord).where(
            WorkspaceOperationRecord.id == operation_id
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return workspace_operation_from_record(record) if record is not None else None

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> WorkspaceOperation | None:
        record = await self._session.scalar(
            select(WorkspaceOperationRecord).where(
                WorkspaceOperationRecord.external_execution_id == external_execution_id,
                WorkspaceOperationRecord.idempotency_key == idempotency_key,
            )
        )
        return workspace_operation_from_record(record) if record is not None else None

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[WorkspaceOperation]:
        records = await self._session.scalars(
            select(WorkspaceOperationRecord)
            .where(WorkspaceOperationRecord.external_execution_id == external_execution_id)
            .order_by(
                WorkspaceOperationRecord.created_at.desc(), WorkspaceOperationRecord.id.desc()
            )
            .limit(limit)
        )
        return [workspace_operation_from_record(record) for record in records]

    async def claim_next(
        self, *, worker_id: str, workspace_scope: str, lease_seconds: int
    ) -> WorkspaceOperation | None:
        now = datetime.now(UTC)
        statement = (
            select(WorkspaceOperationRecord)
            .where(
                WorkspaceOperationRecord.workspace_scope == workspace_scope,
                or_(
                    WorkspaceOperationRecord.status == WorkspaceOperationStatus.PENDING,
                    (
                        (WorkspaceOperationRecord.status == WorkspaceOperationStatus.CLAIMED)
                        & (WorkspaceOperationRecord.lease_expires_at <= now)
                    ),
                ),
            )
            .order_by(WorkspaceOperationRecord.created_at, WorkspaceOperationRecord.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        operation = workspace_operation_from_record(record)
        operation.claim(worker_id, lease_seconds=lease_seconds, at=now)
        self._update(record, operation)
        return operation

    async def save(self, operation: WorkspaceOperation) -> None:
        record = await self._session.get(WorkspaceOperationRecord, operation.id)
        if record is None:
            raise LookupError(f"workspace operation not found: {operation.id}")
        self._update(record, operation)

    @staticmethod
    def _values(operation: WorkspaceOperation) -> dict[str, object]:
        return {
            "id": operation.id,
            "external_execution_id": operation.external_execution_id,
            "kind": operation.kind,
            "target_ref": operation.target_ref,
            "workspace_scope": operation.workspace_scope,
            "idempotency_key": operation.idempotency_key,
            "requested_by": operation.requested_by,
            "status": operation.status,
            "worker_id": operation.worker_id,
            "lease_token": operation.lease_token,
            "lease_expires_at": operation.lease_expires_at,
            "result": operation.result,
            "failure_reason": operation.failure_reason,
            "created_at": operation.created_at,
            "updated_at": operation.updated_at,
            "completed_at": operation.completed_at,
        }

    @classmethod
    def _update(cls, record: WorkspaceOperationRecord, operation: WorkspaceOperation) -> None:
        for key, value in cls._values(operation).items():
            if key != "id":
                setattr(record, key, value)
