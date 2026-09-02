from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.infrastructure.database import Base
from jb_orchestrator.infrastructure.database.workflow_repositories import (
    SqlAlchemyWorkflowDefinitionRepository,
)
from jb_orchestrator.workflows import (
    NodeDefinition,
    NodeKind,
    WorkflowDefinition,
    WorkflowStatus,
)


def definition(key: str, version: int) -> WorkflowDefinition:
    return WorkflowDefinition(
        key=key,
        version=version,
        entry_node="done",
        nodes=(
            NodeDefinition(
                key="done",
                kind=NodeKind.TERMINAL,
                terminal_status=WorkflowStatus.SUCCEEDED,
            ),
        ),
        edges=(),
    )


async def test_workflow_repository_lists_latest_version_per_key() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repository = SqlAlchemyWorkflowDefinitionRepository(session)
        await repository.add(definition("alpha", 1))
        await repository.add(definition("alpha", 2))
        await repository.add(definition("beta", 1))
        await session.commit()

    async with session_factory() as session:
        stored = await SqlAlchemyWorkflowDefinitionRepository(session).list_latest()

    assert [(item.key, item.version) for item in stored] == [("alpha", 2), ("beta", 1)]
    await engine.dispose()
