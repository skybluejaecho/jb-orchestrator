"""SQLAlchemy skill catalog adapter."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import SkillDefinitionRecord
from jb_orchestrator.skills import SkillDefinition


def skill_from_record(record: SkillDefinitionRecord) -> SkillDefinition:
    return SkillDefinition(
        id=record.id,
        key=record.key,
        version=record.version,
        name=record.name,
        description=record.description,
        source_kind=record.source_kind,
        source_uri=record.source_uri,
        content_digest=record.content_digest,
        source_revision=record.source_revision,
        entrypoint=record.entrypoint,
        metadata=record.skill_metadata,
        created_at=record.created_at,
    )


class SqlAlchemySkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, skill: SkillDefinition) -> None:
        self._session.add(
            SkillDefinitionRecord(
                id=skill.id,
                key=skill.key,
                version=skill.version,
                name=skill.name,
                description=skill.description,
                source_kind=skill.source_kind,
                source_uri=skill.source_uri,
                content_digest=skill.content_digest,
                source_revision=skill.source_revision,
                entrypoint=skill.entrypoint,
                skill_metadata=skill.metadata,
                created_at=skill.created_at,
            )
        )

    async def get(self, key: str, version: int | None = None) -> SkillDefinition | None:
        statement = select(SkillDefinitionRecord).where(SkillDefinitionRecord.key == key)
        if version is None:
            statement = statement.order_by(SkillDefinitionRecord.version.desc()).limit(1)
        else:
            statement = statement.where(SkillDefinitionRecord.version == version)
        record = await self._session.scalar(statement)
        return skill_from_record(record) if record is not None else None

    async def list_latest(self) -> list[SkillDefinition]:
        latest = (
            select(
                SkillDefinitionRecord.key,
                func.max(SkillDefinitionRecord.version).label("latest_version"),
            )
            .group_by(SkillDefinitionRecord.key)
            .subquery()
        )
        records = await self._session.scalars(
            select(SkillDefinitionRecord)
            .join(
                latest,
                (SkillDefinitionRecord.key == latest.c.key)
                & (SkillDefinitionRecord.version == latest.c.latest_version),
            )
            .order_by(SkillDefinitionRecord.key)
        )
        return [skill_from_record(record) for record in records]
