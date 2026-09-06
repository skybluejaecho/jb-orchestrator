"""SQLAlchemy adapter for durable worker process presence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import WorkerInstanceRecord
from jb_orchestrator.worker_presence import WorkerInstance, WorkerLifecycleStatus


def worker_instance_from_record(record: WorkerInstanceRecord) -> WorkerInstance:
    return WorkerInstance(
        id=record.id,
        worker_id=record.worker_id,
        kind=record.kind,
        hostname=record.hostname,
        process_id=record.process_id,
        capabilities=tuple(record.capabilities),
        workspace_scope=record.workspace_scope,
        metadata=record.metadata_json,
        status=record.status,
        started_at=record.started_at,
        last_seen_at=record.last_seen_at,
        stopped_at=record.stopped_at,
    )


class SqlAlchemyWorkerInstanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, worker: WorkerInstance) -> None:
        self._session.add(WorkerInstanceRecord(**self._values(worker)))

    async def get(self, instance_id: UUID, *, for_update: bool = False) -> WorkerInstance | None:
        statement = select(WorkerInstanceRecord).where(WorkerInstanceRecord.id == instance_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return worker_instance_from_record(record) if record is not None else None

    async def list(
        self, *, status: WorkerLifecycleStatus | None = None, limit: int = 100
    ) -> list[WorkerInstance]:
        statement = select(WorkerInstanceRecord)
        if status is not None:
            statement = statement.where(WorkerInstanceRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(
                WorkerInstanceRecord.last_seen_at.desc(), WorkerInstanceRecord.id.desc()
            ).limit(limit)
        )
        return [worker_instance_from_record(record) for record in records]

    async def save(self, worker: WorkerInstance) -> None:
        record = await self._session.get(WorkerInstanceRecord, worker.id)
        if record is None:
            raise LookupError(f"worker instance not found: {worker.id}")
        for key, value in self._values(worker).items():
            if key != "id":
                setattr(record, key, value)

    @staticmethod
    def _values(worker: WorkerInstance) -> dict[str, object]:
        return {
            "id": worker.id,
            "worker_id": worker.worker_id,
            "kind": worker.kind,
            "hostname": worker.hostname,
            "process_id": worker.process_id,
            "capabilities": list(worker.capabilities),
            "workspace_scope": worker.workspace_scope,
            "metadata_json": worker.metadata,
            "status": worker.status,
            "started_at": worker.started_at,
            "last_seen_at": worker.last_seen_at,
            "stopped_at": worker.stopped_at,
        }
