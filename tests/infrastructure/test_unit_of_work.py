from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import CreateUserRequest, OrchestrationService, RegisterProject
from jb_orchestrator.domain import RequestStatus, RunStatus
from jb_orchestrator.infrastructure.database import Base, EventRecord, SqlAlchemyUnitOfWork


async def test_application_service_round_trip_with_sqlalchemy() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = OrchestrationService(lambda: SqlAlchemyUnitOfWork(session_factory))

    project = await service.register_project(
        RegisterProject(
            key="jb-orchestrator",
            name="JB Orchestrator",
            repository_url="https://github.com/example/jb-orchestrator.git",
            default_branch="develop",
        )
    )
    created = await service.create_request(
        CreateUserRequest(project_id=project.id, prompt="Build it")
    )
    stored_request = await service.get_request(created.request.id)
    stored_run = await service.get_run(created.run.id)

    assert stored_request.status is RequestStatus.ACTIVE
    assert stored_run.status is RunStatus.QUEUED
    assert (await service.get_project(project.id)).default_branch == "develop"

    cancelled = await service.cancel_run(created.run.id)
    assert cancelled.status is RunStatus.CANCELLED
    assert (await service.get_request(created.request.id)).status is RequestStatus.CANCELLED

    async with session_factory() as session:
        event_types = list(await session.scalars(select(EventRecord.event_type)))
    assert event_types == ["project.registered", "request.created", "run.cancelled"]

    await engine.dispose()
