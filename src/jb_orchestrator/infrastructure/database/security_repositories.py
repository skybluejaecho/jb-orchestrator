"""SQLAlchemy service-account and credential persistence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import (
    ServiceAccountCredentialRecord,
    ServiceAccountRecord,
)
from jb_orchestrator.security import ApiPermission, ServiceAccount, ServiceAccountCredential


def account_from_record(record: ServiceAccountRecord) -> ServiceAccount:
    return ServiceAccount(
        id=record.id,
        key=record.key,
        name=record.name,
        permissions=frozenset(ApiPermission(value) for value in record.permissions),
        project_ids=frozenset(UUID(value) for value in record.project_ids),
        all_projects=record.all_projects,
        enabled=record.enabled,
        created_at=record.created_at,
    )


def credential_from_record(record: ServiceAccountCredentialRecord) -> ServiceAccountCredential:
    return ServiceAccountCredential(
        id=record.id,
        account_id=record.account_id,
        token_digest=record.token_digest,
        created_at=record.created_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        last_used_at=record.last_used_at,
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

    async def list(
        self,
        *,
        enabled: bool | None = None,
        key_prefix: str | None = None,
        after_key: str | None = None,
        limit: int = 100,
    ) -> list[ServiceAccount]:
        statement = select(ServiceAccountRecord)
        if enabled is not None:
            statement = statement.where(ServiceAccountRecord.enabled == enabled)
        if key_prefix is not None:
            statement = statement.where(ServiceAccountRecord.key.startswith(key_prefix))
        if after_key is not None:
            statement = statement.where(ServiceAccountRecord.key > after_key)
        records = await self._session.scalars(
            statement.order_by(ServiceAccountRecord.key).limit(limit)
        )
        return [account_from_record(record) for record in records]

    async def disable(self, account_id: UUID) -> None:
        record = await self._session.get(ServiceAccountRecord, account_id)
        if record is not None:
            record.enabled = False


class SqlAlchemyServiceAccountCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, credential: ServiceAccountCredential) -> None:
        # ServiceAccountRecord and credential records intentionally have no ORM
        # relationship. Flush a newly added account before PostgreSQL enforces
        # the credential foreign key.
        await self._session.flush()
        self._session.add(
            ServiceAccountCredentialRecord(
                id=credential.id,
                account_id=credential.account_id,
                token_digest=credential.token_digest,
                created_at=credential.created_at,
                expires_at=credential.expires_at,
                revoked_at=credential.revoked_at,
                last_used_at=credential.last_used_at,
            )
        )

    async def get(self, credential_id: UUID) -> ServiceAccountCredential | None:
        record = await self._session.get(ServiceAccountCredentialRecord, credential_id)
        return credential_from_record(record) if record is not None else None

    async def list_for_account(self, account_id: UUID) -> list[ServiceAccountCredential]:
        records = await self._session.scalars(
            select(ServiceAccountCredentialRecord)
            .where(ServiceAccountCredentialRecord.account_id == account_id)
            .order_by(
                ServiceAccountCredentialRecord.created_at.desc(),
                ServiceAccountCredentialRecord.id,
            )
        )
        return [credential_from_record(record) for record in records]

    async def list_for_accounts(
        self, account_ids: frozenset[UUID]
    ) -> list[ServiceAccountCredential]:
        if not account_ids:
            return []
        records = await self._session.scalars(
            select(ServiceAccountCredentialRecord)
            .where(ServiceAccountCredentialRecord.account_id.in_(account_ids))
            .order_by(
                ServiceAccountCredentialRecord.account_id,
                ServiceAccountCredentialRecord.created_at.desc(),
                ServiceAccountCredentialRecord.id,
            )
        )
        return [credential_from_record(record) for record in records]

    async def revoke(self, credential_id: UUID, revoked_at: datetime) -> None:
        record = await self._session.get(ServiceAccountCredentialRecord, credential_id)
        if record is not None and record.revoked_at is None:
            record.revoked_at = revoked_at

    async def mark_used(self, credential_id: UUID, used_at: datetime) -> None:
        record = await self._session.get(ServiceAccountCredentialRecord, credential_id)
        if record is None:
            return
        previous = record.last_used_at
        if previous is not None and previous.tzinfo is None:
            previous = previous.replace(tzinfo=UTC)
        if previous is None or previous < used_at:
            record.last_used_at = used_at
