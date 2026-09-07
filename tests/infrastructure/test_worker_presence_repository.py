from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import (
    CreateUserRequest,
    NotificationService,
    OrchestrationService,
    RegisterProject,
    WorkerPresenceService,
    WorkerReadinessService,
    WorkflowService,
)
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.notifications import NotificationEventType
from jb_orchestrator.worker_presence import (
    WorkerKind,
    WorkerLifecycleStatus,
    WorkerReadinessAlertStatus,
)
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)


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


async def test_worker_readiness_alert_round_trips_through_database() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    orchestration = OrchestrationService(factory)
    project = await orchestration.register_project(
        RegisterProject(
            key="worker-alerts",
            name="Worker Alerts",
            repository_url="https://example.com/worker-alerts.git",
        )
    )
    created = await orchestration.create_request(
        CreateUserRequest(project_id=project.id, prompt="Run an unavailable executor")
    )
    workflow = WorkflowService(factory)
    await workflow.register_definition(
        WorkflowDefinition(
            key="unavailable",
            version=1,
            entry_node="work",
            nodes=(
                NodeDefinition(key="work", kind=NodeKind.TASK, executor_key="specialized"),
                NodeDefinition(
                    key="done",
                    kind=NodeKind.TERMINAL,
                    terminal_status=WorkflowStatus.SUCCEEDED,
                ),
            ),
            edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
        )
    )
    await workflow.start(created.run.id, "unavailable", 1)

    now = datetime.now(UTC)
    notification_service = NotificationService(factory)
    subscription, _ = await notification_service.create_subscription(
        project.id,
        provider_key="webhook",
        destination_ref="database-target",
        event_types=(NotificationEventType.WORKER_READINESS_ALERTED,),
        created_by="test",
    )
    service = WorkerReadinessService(factory)
    report = await service.evaluate_project(project.id, at=now, critical_after_seconds=1)
    await service.evaluate_project(
        project.id,
        at=now + timedelta(seconds=2),
        critical_after_seconds=1,
    )

    assert len(report.alerts) == 1
    assert report.alerts[0].status is WorkerReadinessAlertStatus.ACTIVE
    async with factory() as unit_of_work:
        [stored] = await unit_of_work.worker_readiness_alerts.list_by_project(project.id)
    assert stored.id == report.alerts[0].id
    assert stored.executor_key == "specialized"
    assert stored.critical_at is not None
    [delivery] = await notification_service.list_deliveries(project.id)
    assert delivery.subscription_id == subscription.id
    assert delivery.alert_id == stored.id
    assert delivery.event_type is NotificationEventType.WORKER_READINESS_ALERTED
    await engine.dispose()
