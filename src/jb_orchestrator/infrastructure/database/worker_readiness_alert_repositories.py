"""SQLAlchemy adapter for durable worker-readiness alerts."""

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import WorkerReadinessAlertRecord
from jb_orchestrator.worker_presence import WorkerReadinessAlert, WorkerReadinessAlertStatus


def alert_from_record(record: WorkerReadinessAlertRecord) -> WorkerReadinessAlert:
    return WorkerReadinessAlert(
        id=record.id,
        project_id=record.project_id,
        workflow_execution_id=record.workflow_execution_id,
        run_id=record.run_id,
        node_key=record.node_key,
        executor_key=record.executor_key,
        ready_since=record.ready_since,
        reason=record.reason,
        status=record.status,
        first_detected_at=record.first_detected_at,
        last_observed_at=record.last_observed_at,
        critical_at=record.critical_at,
        resolved_at=record.resolved_at,
    )


class SqlAlchemyWorkerReadinessAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_acquire_project_evaluation_lock(self, project_id: UUID) -> bool:
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            return True
        acquired = await self._session.scalar(
            select(func.pg_try_advisory_xact_lock(_project_evaluation_lock_key(project_id)))
        )
        return bool(acquired)

    async def add(self, alert: WorkerReadinessAlert) -> None:
        self._session.add(WorkerReadinessAlertRecord(**self._values(alert)))

    async def get_occurrence(
        self,
        *,
        workflow_execution_id: UUID,
        node_key: str,
        ready_since: datetime,
        for_update: bool = False,
    ) -> WorkerReadinessAlert | None:
        statement = select(WorkerReadinessAlertRecord).where(
            WorkerReadinessAlertRecord.workflow_execution_id == workflow_execution_id,
            WorkerReadinessAlertRecord.node_key == node_key,
            WorkerReadinessAlertRecord.ready_since == ready_since,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return alert_from_record(record) if record is not None else None

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: WorkerReadinessAlertStatus | None = None,
        limit: int = 500,
    ) -> list[WorkerReadinessAlert]:
        statement = select(WorkerReadinessAlertRecord).where(
            WorkerReadinessAlertRecord.project_id == project_id
        )
        if status is not None:
            statement = statement.where(WorkerReadinessAlertRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(
                WorkerReadinessAlertRecord.first_detected_at.desc(),
                WorkerReadinessAlertRecord.id,
            ).limit(limit)
        )
        return [alert_from_record(record) for record in records]

    async def save(self, alert: WorkerReadinessAlert) -> None:
        record = await self._session.get(WorkerReadinessAlertRecord, alert.id)
        if record is None:
            raise LookupError(f"worker readiness alert not found: {alert.id}")
        for key, value in self._values(alert).items():
            if key != "id":
                setattr(record, key, value)

    @staticmethod
    def _values(alert: WorkerReadinessAlert) -> dict[str, object]:
        return {
            "id": alert.id,
            "project_id": alert.project_id,
            "workflow_execution_id": alert.workflow_execution_id,
            "run_id": alert.run_id,
            "node_key": alert.node_key,
            "executor_key": alert.executor_key,
            "ready_since": alert.ready_since,
            "reason": alert.reason,
            "status": alert.status,
            "first_detected_at": alert.first_detected_at,
            "last_observed_at": alert.last_observed_at,
            "critical_at": alert.critical_at,
            "resolved_at": alert.resolved_at,
        }


def _project_evaluation_lock_key(project_id: UUID) -> int:
    digest = hashlib.blake2b(
        project_id.bytes,
        digest_size=8,
        person=b"jb-ready",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)
