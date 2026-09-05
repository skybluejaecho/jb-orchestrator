"""SQLAlchemy adapter for durable SCM publication requests."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import ScmPublicationRecord
from jb_orchestrator.scm import ScmPublication, ScmPublicationStatus


def scm_publication_from_record(record: ScmPublicationRecord) -> ScmPublication:
    return ScmPublication(
        id=record.id,
        external_execution_id=record.external_execution_id,
        provider_key=record.provider_key,
        repository=record.repository,
        source_branch=record.source_branch,
        target_branch=record.target_branch,
        title=record.title,
        body=record.body,
        workspace_scope=record.workspace_scope,
        idempotency_key=record.idempotency_key,
        requested_by=record.requested_by,
        status=record.status,
        worker_id=record.worker_id,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        result=record.result,
        failure_reason=record.failure_reason,
        attempt_count=record.attempt_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class SqlAlchemyScmPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_add(self, publication: ScmPublication) -> bool:
        dialect_name = self._session.get_bind().dialect.name
        values = self._values(publication)
        if dialect_name == "postgresql":
            inserted_id = await self._session.scalar(
                postgresql_insert(ScmPublicationRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["external_execution_id", "idempotency_key"])
                .returning(ScmPublicationRecord.id)
            )
        elif dialect_name == "sqlite":
            inserted_id = await self._session.scalar(
                sqlite_insert(ScmPublicationRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["external_execution_id", "idempotency_key"])
                .returning(ScmPublicationRecord.id)
            )
        else:
            raise RuntimeError(f"unsupported SCM publication database: {dialect_name}")
        return inserted_id is not None

    async def get(self, publication_id: UUID, *, for_update: bool = False) -> ScmPublication | None:
        statement = select(ScmPublicationRecord).where(ScmPublicationRecord.id == publication_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return scm_publication_from_record(record) if record is not None else None

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> ScmPublication | None:
        record = await self._session.scalar(
            select(ScmPublicationRecord).where(
                ScmPublicationRecord.external_execution_id == external_execution_id,
                ScmPublicationRecord.idempotency_key == idempotency_key,
            )
        )
        return scm_publication_from_record(record) if record is not None else None

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[ScmPublication]:
        records = await self._session.scalars(
            select(ScmPublicationRecord)
            .where(ScmPublicationRecord.external_execution_id == external_execution_id)
            .order_by(ScmPublicationRecord.created_at.desc(), ScmPublicationRecord.id.desc())
            .limit(limit)
        )
        return [scm_publication_from_record(record) for record in records]

    async def claim_next(
        self, *, worker_id: str, provider_key: str, workspace_scope: str, lease_seconds: int
    ) -> ScmPublication | None:
        now = datetime.now(UTC)
        statement = (
            select(ScmPublicationRecord)
            .where(
                ScmPublicationRecord.provider_key == provider_key,
                ScmPublicationRecord.workspace_scope == workspace_scope,
                or_(
                    ScmPublicationRecord.status == ScmPublicationStatus.PENDING,
                    (
                        (ScmPublicationRecord.status == ScmPublicationStatus.CLAIMED)
                        & (ScmPublicationRecord.lease_expires_at <= now)
                    ),
                ),
            )
            .order_by(ScmPublicationRecord.created_at, ScmPublicationRecord.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        publication = scm_publication_from_record(record)
        publication.claim(worker_id, lease_seconds=lease_seconds, at=now)
        self._update(record, publication)
        return publication

    async def save(self, publication: ScmPublication) -> None:
        record = await self._session.get(ScmPublicationRecord, publication.id)
        if record is None:
            raise LookupError(f"SCM publication not found: {publication.id}")
        self._update(record, publication)

    @staticmethod
    def _values(publication: ScmPublication) -> dict[str, object]:
        return {
            "id": publication.id,
            "external_execution_id": publication.external_execution_id,
            "provider_key": publication.provider_key,
            "repository": publication.repository,
            "source_branch": publication.source_branch,
            "target_branch": publication.target_branch,
            "title": publication.title,
            "body": publication.body,
            "workspace_scope": publication.workspace_scope,
            "idempotency_key": publication.idempotency_key,
            "requested_by": publication.requested_by,
            "status": publication.status,
            "worker_id": publication.worker_id,
            "lease_token": publication.lease_token,
            "lease_expires_at": publication.lease_expires_at,
            "result": publication.result,
            "failure_reason": publication.failure_reason,
            "attempt_count": publication.attempt_count,
            "created_at": publication.created_at,
            "updated_at": publication.updated_at,
            "completed_at": publication.completed_at,
        }

    @classmethod
    def _update(cls, record: ScmPublicationRecord, publication: ScmPublication) -> None:
        for key, value in cls._values(publication).items():
            if key != "id":
                setattr(record, key, value)
