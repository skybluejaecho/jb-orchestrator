from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import WorkerPresenceService, WorkerReadinessService
from jb_orchestrator.domain import Project, ProjectStatus, Run, UserRequest
from jb_orchestrator.worker_presence import (
    WorkerKind,
    WorkerReadinessAlertStatus,
    WorkerReadinessIssueReason,
)
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowSnapshot,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def ready_execution(store: MemoryStore, project: Project, executor_key: str) -> WorkflowExecution:
    request = UserRequest(project_id=project.id, prompt=f"Run {executor_key}")
    run = Run(request_id=request.id)
    definition = WorkflowDefinition(
        key=f"delivery-{executor_key}",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(key="work", kind=NodeKind.TASK, executor_key=executor_key),
            NodeDefinition(
                key="done",
                kind=NodeKind.TERMINAL,
                terminal_status=WorkflowStatus.SUCCEEDED,
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(definition, run_id=run.id)
    )
    execution.status = WorkflowStatus.RUNNING
    execution.nodes["work"].status = NodeExecutionStatus.READY
    store.requests[request.id] = request
    store.runs[run.id] = run
    store.workflow_executions[execution.id] = execution
    return execution


async def test_readiness_explains_missing_and_offline_capabilities() -> None:
    store = MemoryStore()
    project = Project(
        key="example-project",
        name="Example",
        repository_url="https://github.com/example/project.git",
    )
    store.projects[project.id] = project
    openclaw_execution = ready_execution(store, project, "openclaw")
    unknown_execution = ready_execution(store, project, "specialized")
    presence = WorkerPresenceService(lambda: MemoryUnitOfWork(store))
    now = datetime(2026, 9, 6, tzinfo=UTC)
    stopped = await presence.register(
        worker_id="worker-openclaw",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=42,
        capabilities=("openclaw",),
    )
    await presence.stop(stopped.id, at=now - timedelta(seconds=10))
    await presence.register(
        worker_id="worker-codex",
        kind=WorkerKind.EXECUTION,
        hostname="host-b",
        process_id=43,
        capabilities=("codex",),
    )

    report = await WorkerReadinessService(lambda: MemoryUnitOfWork(store)).inspect_project(
        project.id, at=now
    )

    assert report.online_execution_workers == 1
    assert {issue.workflow_execution_id: issue.reason for issue in report.issues} == {
        openclaw_execution.id: WorkerReadinessIssueReason.CAPABLE_WORKERS_OFFLINE,
        unknown_execution.id: WorkerReadinessIssueReason.NO_CAPABLE_WORKER,
    }
    coverage = {item.executor_key: item for item in report.coverage}
    assert coverage["openclaw"].stopped_worker_ids == ("worker-openclaw",)
    assert coverage["specialized"].online_worker_ids == ()


async def test_readiness_api_reports_covered_ready_task() -> None:
    store = MemoryStore()
    project = Project(
        key="example-project",
        name="Example",
        repository_url="https://github.com/example/project.git",
    )
    store.projects[project.id] = project
    ready_execution(store, project, "openclaw")
    await WorkerPresenceService(lambda: MemoryUnitOfWork(store)).register(
        worker_id="worker-openclaw",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=42,
        capabilities=("openclaw",),
    )
    service = WorkerReadinessService(lambda: MemoryUnitOfWork(store))
    app = create_app(worker_readiness_service=service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{project.id}/worker-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["online_execution_workers"] == 1
    assert payload["issues"] == []
    assert payload["coverage"][0]["online_worker_ids"] == ["worker-openclaw"]


async def test_evaluation_deduplicates_and_resolves_durable_alerts() -> None:
    store = MemoryStore()
    project = Project(
        key="alert-project",
        name="Alert Project",
        repository_url="https://github.com/example/alerts.git",
    )
    store.projects[project.id] = project
    execution = ready_execution(store, project, "openclaw")
    now = datetime.now(UTC)
    execution.nodes["work"].updated_at = now - timedelta(minutes=2)
    service = WorkerReadinessService(lambda: MemoryUnitOfWork(store))

    first = await service.evaluate_project(project.id, at=now)
    second = await service.evaluate_project(project.id, at=now + timedelta(seconds=30))

    assert len(first.alerts) == 1
    assert len(second.alerts) == 1
    alert = second.alerts[0]
    assert alert.id == first.alerts[0].id
    assert alert.first_detected_at == now
    assert alert.last_observed_at == now + timedelta(seconds=30)
    assert [event.event_type for event in store.events] == ["worker.readiness_alerted"]

    presence = WorkerPresenceService(lambda: MemoryUnitOfWork(store))
    stopped = await presence.register(
        worker_id="worker-openclaw-stopped",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=41,
        capabilities=("openclaw",),
    )
    await presence.stop(stopped.id, at=now + timedelta(seconds=40))
    changed = await service.evaluate_project(project.id, at=now + timedelta(seconds=45))

    assert changed.alerts[0].id == alert.id
    assert changed.alerts[0].reason is WorkerReadinessIssueReason.CAPABLE_WORKERS_OFFLINE

    await presence.register(
        worker_id="worker-openclaw",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=42,
        capabilities=("openclaw",),
    )
    resolved = await service.evaluate_project(project.id, at=now + timedelta(seconds=60))

    assert resolved.issues == ()
    assert resolved.alerts[0].status is WorkerReadinessAlertStatus.RESOLVED
    assert resolved.alerts[0].resolved_at == now + timedelta(seconds=60)
    assert [event.event_type for event in store.events] == [
        "worker.readiness_alerted",
        "worker.readiness_alert_reason_changed",
        "worker.readiness_resolved",
    ]


async def test_evaluation_api_returns_alert_severity_and_recovery_action() -> None:
    store = MemoryStore()
    project = Project(
        key="alert-api-project",
        name="Alert API",
        repository_url="https://github.com/example/alert-api.git",
    )
    store.projects[project.id] = project
    execution = ready_execution(store, project, "specialized")
    now = datetime.now(UTC)
    execution.nodes["work"].updated_at = now - timedelta(minutes=10)
    service = WorkerReadinessService(lambda: MemoryUnitOfWork(store))
    app = create_app(worker_readiness_service=service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/v1/projects/{project.id}/worker-readiness/evaluate")

    assert response.status_code == 200
    [alert] = response.json()["alerts"]
    assert alert["status"] == "active"
    assert alert["severity"] == "warning"
    assert alert["recommended_action"] == "start_capable_worker"


async def test_active_project_evaluation_escalates_once_and_skips_archived_projects() -> None:
    store = MemoryStore()
    active = Project(
        key="active-alerts",
        name="Active Alerts",
        repository_url="https://github.com/example/active.git",
    )
    archived = Project(
        key="archived-alerts",
        name="Archived Alerts",
        repository_url="https://github.com/example/archived.git",
        status=ProjectStatus.ARCHIVED,
    )
    store.projects[active.id] = active
    store.projects[archived.id] = archived
    ready_execution(store, active, "openclaw")
    ready_execution(store, archived, "specialized")
    service = WorkerReadinessService(lambda: MemoryUnitOfWork(store))
    now = datetime.now(UTC)

    first = await service.evaluate_active_projects(at=now, critical_after_seconds=30)
    second = await service.evaluate_active_projects(
        at=now + timedelta(seconds=31), critical_after_seconds=30
    )
    third = await service.evaluate_active_projects(
        at=now + timedelta(seconds=60), critical_after_seconds=30
    )

    assert [report.project_id for report in first] == [active.id]
    assert second[0].alerts[0].critical_at == now + timedelta(seconds=31)
    assert third[0].alerts[0].critical_at == now + timedelta(seconds=31)
    assert [event.event_type for event in store.events] == [
        "worker.readiness_alerted",
        "worker.readiness_critical",
    ]
