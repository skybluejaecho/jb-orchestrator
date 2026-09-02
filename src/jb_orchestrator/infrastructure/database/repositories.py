"""SQLAlchemy implementations of domain repository ports."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.domain import DomainEvent, Project, Run, UserRequest
from jb_orchestrator.infrastructure.database.models import (
    EventRecord,
    ProjectRecord,
    RunRecord,
    UserRequestRecord,
)


def project_from_record(record: ProjectRecord) -> Project:
    return Project(
        id=record.id,
        key=record.key,
        name=record.name,
        repository_url=record.repository_url,
        default_branch=record.default_branch,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def request_from_record(record: UserRequestRecord) -> UserRequest:
    return UserRequest(
        id=record.id,
        project_id=record.project_id,
        title=record.title,
        prompt=record.prompt,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def run_from_record(record: RunRecord) -> Run:
    return Run(
        id=record.id,
        request_id=record.request_id,
        attempt=record.attempt,
        status=record.status,
        failure_reason=record.failure_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        version=record.version,
    )


def event_from_record(record: EventRecord) -> DomainEvent:
    return DomainEvent(
        id=record.id,
        aggregate_type=record.aggregate_type,
        aggregate_id=record.aggregate_id,
        event_type=record.event_type,
        payload=record.payload,
        sequence=record.sequence,
        occurred_at=record.occurred_at,
    )


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: Project) -> None:
        self._session.add(
            ProjectRecord(
                id=project.id,
                key=project.key,
                name=project.name,
                repository_url=project.repository_url,
                default_branch=project.default_branch,
                status=project.status,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )

    async def get(self, project_id: UUID) -> Project | None:
        record = await self._session.get(ProjectRecord, project_id)
        return project_from_record(record) if record is not None else None

    async def get_by_key(self, key: str) -> Project | None:
        record = await self._session.scalar(select(ProjectRecord).where(ProjectRecord.key == key))
        return project_from_record(record) if record is not None else None


class SqlAlchemyUserRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, request: UserRequest) -> None:
        self._session.add(
            UserRequestRecord(
                id=request.id,
                project_id=request.project_id,
                title=request.title,
                prompt=request.prompt,
                status=request.status,
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
        )

    async def get(self, request_id: UUID) -> UserRequest | None:
        record = await self._session.get(UserRequestRecord, request_id)
        return request_from_record(record) if record is not None else None

    async def save(self, request: UserRequest) -> None:
        record = await self._session.get(UserRequestRecord, request.id)
        if record is None:
            await self.add(request)
            return
        record.status = request.status
        record.updated_at = request.updated_at


class SqlAlchemyRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: Run) -> None:
        self._session.add(
            RunRecord(
                id=run.id,
                request_id=run.request_id,
                attempt=run.attempt,
                status=run.status,
                failure_reason=run.failure_reason,
                created_at=run.created_at,
                updated_at=run.updated_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
                version=run.version,
            )
        )

    async def get(self, run_id: UUID) -> Run | None:
        record = await self._session.get(RunRecord, run_id)
        return run_from_record(record) if record is not None else None

    async def save(self, run: Run) -> None:
        record = await self._session.get(RunRecord, run.id)
        if record is None:
            await self.add(run)
            return
        record.status = run.status
        record.failure_reason = run.failure_reason
        record.updated_at = run.updated_at
        record.started_at = run.started_at
        record.completed_at = run.completed_at
        record.version = run.version


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: DomainEvent) -> None:
        self._session.add(
            EventRecord(
                id=event.id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
        )

    async def get(self, event_id: UUID) -> DomainEvent | None:
        record = await self._session.scalar(select(EventRecord).where(EventRecord.id == event_id))
        return event_from_record(record) if record is not None else None

    async def list_after(
        self,
        *,
        aggregate_type: str,
        after: DomainEvent | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        statement = select(EventRecord).where(EventRecord.aggregate_type == aggregate_type)
        if after is not None:
            if after.sequence is None:
                raise ValueError("persisted event cursor requires a sequence")
            statement = statement.where(EventRecord.sequence > after.sequence)
        records = await self._session.scalars(statement.order_by(EventRecord.sequence).limit(limit))
        return [event_from_record(record) for record in records]
