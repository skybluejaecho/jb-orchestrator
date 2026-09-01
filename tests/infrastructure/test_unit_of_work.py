from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import (
    CreateUserRequest,
    OrchestrationService,
    RegisterProject,
    WorkflowService,
)
from jb_orchestrator.domain import RequestStatus, RunStatus
from jb_orchestrator.infrastructure.database import Base, EventRecord, SqlAlchemyUnitOfWork
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)


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

    workflow_service = WorkflowService(lambda: SqlAlchemyUnitOfWork(session_factory))
    definition = WorkflowDefinition(
        key="delivery",
        version=1,
        entry_node="implement",
        nodes=(
            NodeDefinition(key="implement", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="implement", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(created.run.id, "delivery")
    await workflow_service.begin_task(execution.id, "implement")
    completed_execution = await workflow_service.complete_task(
        execution.id, "implement", NodeOutcome.SUCCESS, {"commit": "abc123"}
    )
    stored_execution = await workflow_service.get(execution.id)
    assert stored_execution.status is WorkflowStatus.SUCCEEDED
    assert stored_execution.nodes["implement"].status is NodeExecutionStatus.SUCCEEDED
    assert stored_execution.nodes["implement"].output == {"commit": "abc123"}
    assert stored_execution.version == completed_execution.version

    cancelled = await service.cancel_run(created.run.id)
    assert cancelled.status is RunStatus.CANCELLED
    assert (await service.get_request(created.request.id)).status is RequestStatus.CANCELLED

    async with session_factory() as session:
        event_types = list(await session.scalars(select(EventRecord.event_type)))
    assert sorted(event_types) == sorted(
        [
            "project.registered",
            "request.created",
            "workflow.definition_registered",
            "workflow.started",
            "workflow.node_started",
            "workflow.node_completed",
            "run.cancelled",
        ]
    )

    await engine.dispose()
