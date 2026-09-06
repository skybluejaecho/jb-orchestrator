from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import WorkerPresenceService
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.worker_presence import WorkerKind, WorkerLifecycleStatus


async def test_worker_presence_round_trips_through_database() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = WorkerPresenceService(lambda: SqlAlchemyUnitOfWork(session_factory))

    worker = await service.register(
        worker_id="scm-a",
        kind=WorkerKind.SCM,
        hostname="host-a",
        process_id=42,
        capabilities=("github",),
        workspace_scope="git-worktree:scope-a",
    )
    await service.heartbeat(worker.id)
    await service.stop(worker.id)
    [view] = await service.list()

    assert view.worker.id == worker.id
    assert view.worker.status is WorkerLifecycleStatus.STOPPED
    assert view.worker.capabilities == ("github",)
    await engine.dispose()
