"""SQLAlchemy adapter for project workflow bindings."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import ProjectWorkflowBindingRecord
from jb_orchestrator.workflows.bindings import ProjectWorkflowBinding


def binding_from_record(record: ProjectWorkflowBindingRecord) -> ProjectWorkflowBinding:
    return ProjectWorkflowBinding(
        id=record.id,
        project_id=record.project_id,
        definition_id=record.definition_id,
        definition_key=record.definition_key,
        definition_version=record.definition_version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlAlchemyProjectWorkflowBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> ProjectWorkflowBinding | None:
        statement = select(ProjectWorkflowBindingRecord).where(
            ProjectWorkflowBindingRecord.project_id == project_id
        )
        if for_update:
            statement = statement.with_for_update()
        record = await self._session.scalar(statement)
        return binding_from_record(record) if record is not None else None

    async def save(self, binding: ProjectWorkflowBinding) -> None:
        record = await self._session.scalar(
            select(ProjectWorkflowBindingRecord).where(
                ProjectWorkflowBindingRecord.project_id == binding.project_id
            )
        )
        if record is None:
            self._session.add(
                ProjectWorkflowBindingRecord(
                    id=binding.id,
                    project_id=binding.project_id,
                    definition_id=binding.definition_id,
                    definition_key=binding.definition_key,
                    definition_version=binding.definition_version,
                    created_at=binding.created_at,
                    updated_at=binding.updated_at,
                )
            )
            return
        record.definition_id = binding.definition_id
        record.definition_key = binding.definition_key
        record.definition_version = binding.definition_version
        record.updated_at = binding.updated_at
