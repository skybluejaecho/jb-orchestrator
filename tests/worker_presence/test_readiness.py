from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import WorkerPresenceService, WorkerReadinessService
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.worker_presence import (
    WorkerKind,
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
