"""SQLAlchemy adapter for versioned phase packs."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import PhasePackDefinitionRecord
from jb_orchestrator.phase_packs import PhasePackDefinition
from jb_orchestrator.phase_packs.serialization import phase_pack_from_dict, phase_pack_to_dict


def phase_pack_from_record(record: PhasePackDefinitionRecord) -> PhasePackDefinition:
    return phase_pack_from_dict(
        {
            "id": str(record.id),
            "key": record.key,
            "version": record.version,
            "name": record.name,
            "description": record.description,
            "instructions": record.instructions,
            "inputs": record.inputs,
            "output_contract": record.output_contract,
            "skills": record.skills,
            "metadata": record.phase_metadata,
            "created_at": record.created_at.isoformat(),
        }
    )


class SqlAlchemyPhasePackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, phase_pack: PhasePackDefinition) -> None:
        data = phase_pack_to_dict(phase_pack)
        self._session.add(
            PhasePackDefinitionRecord(
                id=phase_pack.id,
                key=phase_pack.key,
                version=phase_pack.version,
                name=phase_pack.name,
                description=phase_pack.description,
                instructions=phase_pack.instructions,
                inputs=data["inputs"],
                output_contract=phase_pack.output_contract,
                skills=data["skills"],
                phase_metadata=phase_pack.metadata,
                created_at=phase_pack.created_at,
            )
        )

    async def get(self, key: str, version: int | None = None) -> PhasePackDefinition | None:
        statement = select(PhasePackDefinitionRecord).where(PhasePackDefinitionRecord.key == key)
        if version is None:
            statement = statement.order_by(PhasePackDefinitionRecord.version.desc()).limit(1)
        else:
            statement = statement.where(PhasePackDefinitionRecord.version == version)
        record = await self._session.scalar(statement)
        return phase_pack_from_record(record) if record is not None else None

    async def list_latest(self) -> list[PhasePackDefinition]:
        latest = (
            select(
                PhasePackDefinitionRecord.key,
                func.max(PhasePackDefinitionRecord.version).label("latest_version"),
            )
            .group_by(PhasePackDefinitionRecord.key)
            .subquery()
        )
        records = await self._session.scalars(
            select(PhasePackDefinitionRecord)
            .join(
                latest,
                (PhasePackDefinitionRecord.key == latest.c.key)
                & (PhasePackDefinitionRecord.version == latest.c.latest_version),
            )
            .order_by(PhasePackDefinitionRecord.key)
        )
        return [phase_pack_from_record(record) for record in records]
