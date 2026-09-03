"""SQLAlchemy idempotent request dispatch receipt adapter."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.domain.dispatches import RequestDispatchReceipt
from jb_orchestrator.infrastructure.database.models import RequestDispatchReceiptRecord


def receipt_from_record(record: RequestDispatchReceiptRecord) -> RequestDispatchReceipt:
    return RequestDispatchReceipt(
        id=record.id,
        project_id=record.project_id,
        idempotency_key=record.idempotency_key,
        payload_digest=record.payload_digest,
        request_id=record.request_id,
        run_id=record.run_id,
        workflow_execution_id=record.workflow_execution_id,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


class SqlAlchemyRequestDispatchReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_claim(self, receipt: RequestDispatchReceipt) -> bool:
        values = {
            "id": receipt.id,
            "project_id": receipt.project_id,
            "idempotency_key": receipt.idempotency_key,
            "payload_digest": receipt.payload_digest,
            "created_at": receipt.created_at,
        }
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            claimed_id = await self._session.scalar(
                postgresql_insert(RequestDispatchReceiptRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["project_id", "idempotency_key"])
                .returning(RequestDispatchReceiptRecord.id)
            )
        elif dialect_name == "sqlite":
            claimed_id = await self._session.scalar(
                sqlite_insert(RequestDispatchReceiptRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["project_id", "idempotency_key"])
                .returning(RequestDispatchReceiptRecord.id)
            )
        else:
            raise RuntimeError(f"unsupported dispatch claim database dialect: {dialect_name}")
        return claimed_id is not None

    async def get(
        self, project_id: UUID, idempotency_key: str, *, for_update: bool = False
    ) -> RequestDispatchReceipt | None:
        statement = select(RequestDispatchReceiptRecord).where(
            RequestDispatchReceiptRecord.project_id == project_id,
            RequestDispatchReceiptRecord.idempotency_key == idempotency_key,
        )
        if for_update:
            statement = statement.with_for_update()
        record = await self._session.scalar(statement)
        return receipt_from_record(record) if record is not None else None

    async def save(self, receipt: RequestDispatchReceipt) -> None:
        record = await self._session.get(RequestDispatchReceiptRecord, receipt.id)
        if record is None:
            raise RuntimeError(f"dispatch receipt not found: {receipt.id}")
        record.request_id = receipt.request_id
        record.run_id = receipt.run_id
        record.workflow_execution_id = receipt.workflow_execution_id
        record.completed_at = receipt.completed_at
