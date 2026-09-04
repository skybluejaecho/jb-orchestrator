from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import ExternalExecutionService
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.worker import TaskClaim


async def test_external_workspace_metadata_round_trips_through_sqlalchemy() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ExternalExecutionService(lambda: SqlAlchemyUnitOfWork(session_factory))
    claim = TaskClaim(
        execution_id=uuid4(),
        run_id=uuid4(),
        node_key="implement",
        executor_key="openclaw",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key="execution:implement:1",
        visit_count=1,
        attempt_count=1,
        timeout_seconds=300,
        workflow_key="delivery",
        workflow_version=1,
        instructions=None,
        configuration={},
        skills=(),
    )

    created = await service.prepare(
        claim,
        session_key="agent:implementation:execution",
        agent_id="implementation",
        workspace_path="C:/worktrees/implement",
        workspace_branch="jb/execution/implement-v1",
        workspace_base_ref="a" * 40,
    )
    loaded = await service.get(claim.idempotency_key)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.workspace_path == "C:/worktrees/implement"
    assert loaded.workspace_branch == "jb/execution/implement-v1"
    assert loaded.workspace_base_ref == "a" * 40
    await engine.dispose()
