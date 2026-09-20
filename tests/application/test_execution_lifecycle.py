import pytest

from jb_orchestrator.application import (
    CreatedRequest,
    CreateUserRequest,
    OrchestrationService,
    RegisterProject,
    WorkflowService,
)
from jb_orchestrator.application.exceptions import ResourceConflict
from jb_orchestrator.domain import RequestStatus, RunStatus
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def failing_definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        key="failing",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(key="work", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )


async def create_context() -> tuple[
    MemoryStore, OrchestrationService, WorkflowService, CreatedRequest
]:
    store = MemoryStore()
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    orchestration = OrchestrationService(factory)
    workflows = WorkflowService(factory)
    project = await orchestration.register_project(
        RegisterProject(
            key="lifecycle-project",
            name="Lifecycle Project",
            repository_url="https://example.com/lifecycle.git",
        )
    )
    created = await orchestration.create_request(
        CreateUserRequest(project_id=project.id, prompt="Exercise lifecycle")
    )
    await workflows.register_definition(failing_definition())
    return store, orchestration, workflows, created


async def test_failed_workflow_fails_run_but_keeps_request_active_for_retry() -> None:
    store, _, workflows, created = await create_context()
    execution = await workflows.start(created.run.id, "failing")
    await workflows.begin_task(execution.id, "work")

    failed = await workflows.fail_task(execution.id, "work", "executor unavailable")

    assert failed.status is WorkflowStatus.FAILED
    assert store.runs[created.run.id].status is RunStatus.FAILED
    assert store.runs[created.run.id].failure_reason == "executor unavailable"
    assert store.requests[created.request.id].status is RequestStatus.ACTIVE
    assert [event.event_type for event in store.events[-2:]] == [
        "workflow.node_failed",
        "run.status_changed",
    ]


async def test_run_cancel_cancels_its_active_workflow_and_request() -> None:
    store, orchestration, workflows, created = await create_context()
    execution = await workflows.start(created.run.id, "failing")

    cancelled = await orchestration.cancel_run(created.run.id)

    assert cancelled.status is RunStatus.CANCELLED
    assert store.workflow_executions[execution.id].status is WorkflowStatus.CANCELLED
    assert store.requests[created.request.id].status is RequestStatus.CANCELLED
    assert [event.event_type for event in store.events[-3:]] == [
        "workflow.cancelled",
        "run.status_changed",
        "request.cancelled",
    ]


async def test_legacy_run_approval_is_rejected_when_workflow_exists() -> None:
    _, orchestration, workflows, created = await create_context()
    await workflows.start(created.run.id, "failing")

    with pytest.raises(ResourceConflict, match="specific approval node"):
        await orchestration.approve_run(created.run.id)
