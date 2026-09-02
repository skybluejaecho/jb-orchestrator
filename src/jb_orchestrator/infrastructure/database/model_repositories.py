"""SQLAlchemy model profile catalog adapter."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import ModelProfileRecord
from jb_orchestrator.model_routing import ModelProfile


def profile_from_record(record: ModelProfileRecord) -> ModelProfile:
    return ModelProfile(
        id=record.id,
        key=record.key,
        version=record.version,
        name=record.name,
        provider=record.provider,
        model_id=record.model_id,
        tier=record.tier,
        context_window=record.context_window,
        input_cost_per_million=record.input_cost_per_million,
        output_cost_per_million=record.output_cost_per_million,
        enabled=record.enabled,
        capabilities=tuple(record.capabilities),
        executor_keys=tuple(record.executor_keys),
        metadata=record.profile_metadata,
        created_at=record.created_at,
    )


class SqlAlchemyModelProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, profile: ModelProfile) -> None:
        self._session.add(
            ModelProfileRecord(
                id=profile.id,
                key=profile.key,
                version=profile.version,
                name=profile.name,
                provider=profile.provider,
                model_id=profile.model_id,
                tier=profile.tier,
                context_window=profile.context_window,
                input_cost_per_million=profile.input_cost_per_million,
                output_cost_per_million=profile.output_cost_per_million,
                enabled=profile.enabled,
                capabilities=list(profile.capabilities),
                executor_keys=list(profile.executor_keys),
                profile_metadata=profile.metadata,
                created_at=profile.created_at,
            )
        )

    async def get(self, key: str, version: int | None = None) -> ModelProfile | None:
        statement = select(ModelProfileRecord).where(ModelProfileRecord.key == key)
        if version is None:
            statement = statement.order_by(ModelProfileRecord.version.desc()).limit(1)
        else:
            statement = statement.where(ModelProfileRecord.version == version)
        record = await self._session.scalar(statement)
        return profile_from_record(record) if record is not None else None

    async def list_latest(self) -> list[ModelProfile]:
        latest = (
            select(
                ModelProfileRecord.key,
                func.max(ModelProfileRecord.version).label("latest_version"),
            )
            .group_by(ModelProfileRecord.key)
            .subquery()
        )
        records = await self._session.scalars(
            select(ModelProfileRecord)
            .join(
                latest,
                (ModelProfileRecord.key == latest.c.key)
                & (ModelProfileRecord.version == latest.c.latest_version),
            )
            .order_by(ModelProfileRecord.key)
        )
        return [profile_from_record(record) for record in records]
