"""SQLAlchemy adapter for immutable task artifacts."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.infrastructure.database.models import TaskArtifactRecord


def artifact_from_record(record: TaskArtifactRecord) -> TaskArtifact:
    return TaskArtifact(
        id=record.id,
        execution_id=record.execution_id,
        producer_node_key=record.producer_node_key,
        visit_count=record.visit_count,
        outcome=record.outcome,
        content=record.content,
        created_at=record.created_at,
    )


class SqlAlchemyTaskArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, artifact: TaskArtifact) -> None:
        self._session.add(
            TaskArtifactRecord(
                id=artifact.id,
                execution_id=artifact.execution_id,
                producer_node_key=artifact.producer_node_key,
                visit_count=artifact.visit_count,
                outcome=artifact.outcome,
                content=artifact.content,
                created_at=artifact.created_at,
            )
        )

    async def list_for_execution(self, execution_id: UUID) -> list[TaskArtifact]:
        records = await self._session.scalars(
            select(TaskArtifactRecord)
            .where(TaskArtifactRecord.execution_id == execution_id)
            .order_by(TaskArtifactRecord.created_at, TaskArtifactRecord.id)
        )
        return [artifact_from_record(record) for record in records]

    async def list_latest_for_nodes(
        self, execution_id: UUID, node_keys: Collection[str]
    ) -> list[TaskArtifact]:
        if not node_keys:
            return []
        latest_visits = (
            select(
                TaskArtifactRecord.producer_node_key,
                func.max(TaskArtifactRecord.visit_count).label("visit_count"),
            )
            .where(
                TaskArtifactRecord.execution_id == execution_id,
                TaskArtifactRecord.producer_node_key.in_(node_keys),
            )
            .group_by(TaskArtifactRecord.producer_node_key)
            .subquery()
        )
        records = await self._session.scalars(
            select(TaskArtifactRecord)
            .join(
                latest_visits,
                (TaskArtifactRecord.producer_node_key == latest_visits.c.producer_node_key)
                & (TaskArtifactRecord.visit_count == latest_visits.c.visit_count),
            )
            .where(TaskArtifactRecord.execution_id == execution_id)
            .order_by(TaskArtifactRecord.producer_node_key)
        )
        return [artifact_from_record(record) for record in records]
