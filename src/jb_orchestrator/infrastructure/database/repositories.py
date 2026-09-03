"""SQLAlchemy implementations of domain repository ports."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.domain import (
    DomainEvent,
    Project,
    ProjectStatus,
    RequestOrigin,
    RequestStatus,
    Run,
    RunStatus,
    UserRequest,
)
from jb_orchestrator.infrastructure.database.models import (
    BudgetAccountRecord,
    BudgetReservationRecord,
    EventRecord,
    ExternalExecutionRecord,
    ProjectRecord,
    RunRecord,
    UserRequestRecord,
    WorkflowExecutionRecord,
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
        origin=(
            RequestOrigin(
                ingress_key=record.ingress_key,
                external_request_id=record.external_request_id,
                actor_id=record.origin_actor_id,
                conversation_id=record.origin_conversation_id,
            )
            if record.ingress_key is not None and record.external_request_id is not None
            else None
        ),
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

    async def list(self, *, status: ProjectStatus | None = None, limit: int = 100) -> list[Project]:
        statement = select(ProjectRecord)
        if status is not None:
            statement = statement.where(ProjectRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(ProjectRecord.created_at.desc(), ProjectRecord.id).limit(limit)
        )
        return [project_from_record(record) for record in records]


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
                ingress_key=request.origin.ingress_key if request.origin is not None else None,
                external_request_id=(
                    request.origin.external_request_id if request.origin is not None else None
                ),
                origin_actor_id=request.origin.actor_id if request.origin is not None else None,
                origin_conversation_id=(
                    request.origin.conversation_id if request.origin is not None else None
                ),
                status=request.status,
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
        )

    async def get(self, request_id: UUID) -> UserRequest | None:
        record = await self._session.get(UserRequestRecord, request_id)
        return request_from_record(record) if record is not None else None

    async def get_for_update(self, request_id: UUID) -> UserRequest | None:
        record = await self._session.scalar(
            select(UserRequestRecord).where(UserRequestRecord.id == request_id).with_for_update()
        )
        return request_from_record(record) if record is not None else None

    async def save(self, request: UserRequest) -> None:
        record = await self._session.get(UserRequestRecord, request.id)
        if record is None:
            await self.add(request)
            return
        record.status = request.status
        record.updated_at = request.updated_at

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: RequestStatus | None = None,
        limit: int = 100,
    ) -> list[UserRequest]:
        statement = select(UserRequestRecord).where(UserRequestRecord.project_id == project_id)
        if status is not None:
            statement = statement.where(UserRequestRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(UserRequestRecord.created_at.desc(), UserRequestRecord.id).limit(
                limit
            )
        )
        return [request_from_record(record) for record in records]


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

    async def get_for_update(self, run_id: UUID) -> Run | None:
        record = await self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
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

    async def list_by_request(
        self,
        request_id: UUID,
        *,
        status: RunStatus | None = None,
        limit: int = 100,
    ) -> list[Run]:
        statement = select(RunRecord).where(RunRecord.request_id == request_id)
        if status is not None:
            statement = statement.where(RunRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(RunRecord.created_at.desc(), RunRecord.id).limit(limit)
        )
        return [run_from_record(record) for record in records]


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

    async def list_project_after(
        self,
        *,
        project_id: UUID,
        after: DomainEvent | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        request_ids = select(UserRequestRecord.id).where(UserRequestRecord.project_id == project_id)
        run_ids = select(RunRecord.id).where(RunRecord.request_id.in_(request_ids))
        workflow_ids = select(WorkflowExecutionRecord.id).where(
            WorkflowExecutionRecord.run_id.in_(run_ids)
        )
        external_ids = select(ExternalExecutionRecord.id).where(
            ExternalExecutionRecord.run_id.in_(run_ids)
        )
        budget_account_ids = select(BudgetAccountRecord.id).where(
            BudgetAccountRecord.project_id == project_id
        )
        budget_reservation_ids = select(BudgetReservationRecord.id).where(
            BudgetReservationRecord.project_id == project_id
        )
        statement = select(EventRecord).where(
            or_(
                and_(
                    EventRecord.aggregate_type == "project",
                    EventRecord.aggregate_id == project_id,
                ),
                and_(
                    EventRecord.aggregate_type == "request",
                    EventRecord.aggregate_id.in_(request_ids),
                ),
                and_(
                    EventRecord.aggregate_type == "run",
                    EventRecord.aggregate_id.in_(run_ids),
                ),
                and_(
                    EventRecord.aggregate_type == "workflow_execution",
                    EventRecord.aggregate_id.in_(workflow_ids),
                ),
                and_(
                    EventRecord.aggregate_type == "external_execution",
                    EventRecord.aggregate_id.in_(external_ids),
                ),
                and_(
                    EventRecord.aggregate_type == "budget_account",
                    EventRecord.aggregate_id.in_(budget_account_ids),
                ),
                and_(
                    EventRecord.aggregate_type == "budget_reservation",
                    EventRecord.aggregate_id.in_(budget_reservation_ids),
                ),
            )
        )
        if after is not None:
            if after.sequence is None:
                raise ValueError("persisted event cursor requires a sequence")
            statement = statement.where(EventRecord.sequence > after.sequence)
        records = await self._session.scalars(statement.order_by(EventRecord.sequence).limit(limit))
        return [event_from_record(record) for record in records]
