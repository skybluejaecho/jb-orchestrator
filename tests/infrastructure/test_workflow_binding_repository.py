from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import (
    OrchestrationService,
    RegisterProject,
    RequestDispatchService,
    WorkflowService,
)
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)


async def test_sqlalchemy_binding_and_dispatch_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    project = await OrchestrationService(factory).register_project(
        RegisterProject(
            key="bound-project",
            name="Bound Project",
            repository_url="https://example.com/bound.git",
        )
    )
    workflow_service = WorkflowService(factory)
    definition = await workflow_service.register_definition(
        WorkflowDefinition(
            key="delivery",
            version=1,
            entry_node="work",
            nodes=(
                NodeDefinition(key="work", kind=NodeKind.TASK),
                NodeDefinition(
                    key="done",
                    kind=NodeKind.TERMINAL,
                    terminal_status=WorkflowStatus.SUCCEEDED,
                ),
            ),
            edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
        )
    )
    service = RequestDispatchService(factory, workflow_service)

    configured = await service.configure_binding(project.id, definition.key, definition.version)
    fetched = await service.get_binding(project.id)
    dispatched = await service.dispatch(
        project.id, "Execute the bound workflow", idempotency_key="sql-round-trip"
    )
    replayed = await service.dispatch(
        project.id, "Execute the bound workflow", idempotency_key="sql-round-trip"
    )
    stored = await workflow_service.get(dispatched.workflow.id)

    assert fetched.id == configured.id
    assert fetched.project_id == configured.project_id
    assert fetched.definition_id == configured.definition_id
    assert (fetched.definition_key, fetched.definition_version) == ("delivery", 1)
    assert stored.snapshot.definition_id == definition.id
    assert stored.snapshot.request_context is not None
    assert stored.snapshot.request_context.request_id == dispatched.request.id
    assert stored.snapshot.run_id == dispatched.run.id
    assert dispatched.run.status.value == "running"
    assert dispatched.run.started_at is not None
    assert replayed.replayed is True
    assert replayed.workflow.id == dispatched.workflow.id

    await engine.dispose()
