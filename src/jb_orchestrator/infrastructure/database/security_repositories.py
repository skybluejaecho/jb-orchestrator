"""SQLAlchemy service-account persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import ServiceAccountRecord
from jb_orchestrator.security import ApiPermission, ServiceAccount


def account_from_record(record: ServiceAccountRecord) -> ServiceAccount:
    return ServiceAccount(
        id=record.id,
        key=record.key,
        name=record.name,
        token_digest=record.token_digest,
        permissions=frozenset(ApiPermission(value) for value in record.permissions),
        project_ids=frozenset(UUID(value) for value in record.project_ids),
        all_projects=record.all_projects,
        enabled=record.enabled,
        created_at=record.created_at,
    )


class SqlAlchemyServiceAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, account: ServiceAccount) -> None:
        self._session.add(
            ServiceAccountRecord(
                id=account.id,
                key=account.key,
                name=account.name,
                token_digest=account.token_digest,
                permissions=[value.value for value in sorted(account.permissions)],
                project_ids=[str(value) for value in sorted(account.project_ids)],
                all_projects=account.all_projects,
                enabled=account.enabled,
                created_at=account.created_at,
            )
        )

    async def get(self, account_id: UUID) -> ServiceAccount | None:
        record = await self._session.get(ServiceAccountRecord, account_id)
        return account_from_record(record) if record is not None else None

    async def get_by_key(self, key: str) -> ServiceAccount | None:
        record = await self._session.scalar(
            select(ServiceAccountRecord).where(ServiceAccountRecord.key == key)
        )
        return account_from_record(record) if record is not None else None

    async def disable(self, account_id: UUID) -> None:
        record = await self._session.get(ServiceAccountRecord, account_id)
        if record is not None:
            record.enabled = False
