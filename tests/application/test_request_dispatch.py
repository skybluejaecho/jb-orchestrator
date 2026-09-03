import pytest

from jb_orchestrator.application import RequestDispatchService, WorkflowService
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import Project
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def definition(version: int) -> WorkflowDefinition:
    return WorkflowDefinition(
        key="delivery",
        version=version,
        entry_node="work",
        nodes=(
            NodeDefinition(key="work", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )


async def test_binding_pins_exact_version_and_dispatches_all_state() -> None:
    store = MemoryStore()
    project = Project(
        key="dispatch-project",
        name="Dispatch Project",
        repository_url="https://example.com/dispatch.git",
        default_branch="develop",
    )
    store.projects[project.id] = project

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    workflows = WorkflowService(unit_of_work_factory)
    service = RequestDispatchService(unit_of_work_factory, workflows)
    first = await workflows.register_definition(definition(1))
    await workflows.register_definition(definition(2))

    binding = await service.configure_binding(project.id, "delivery", 1)
    dispatched = await service.dispatch(project.id, "Ship the requested change", "Delivery")

    assert binding.definition_id == first.id
    assert dispatched.request.id in store.requests
    assert dispatched.run.id in store.runs
    assert dispatched.workflow.id in store.workflow_executions
    assert dispatched.workflow.snapshot.definition_version == 1
    assert dispatched.workflow.snapshot.request_context is not None
    assert dispatched.workflow.snapshot.request_context.prompt == "Ship the requested change"
    assert [event.event_type for event in store.events[-3:]] == [
        "project.workflow_bound",
        "request.created",
        "workflow.started",
    ]
    assert store.events[-1].payload["selection_source"] == "project_binding"


async def test_binding_update_affects_only_future_dispatches() -> None:
    store = MemoryStore()
    project = Project(
        key="versioned-project",
        name="Versioned Project",
        repository_url="https://example.com/versioned.git",
    )
    store.projects[project.id] = project
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    service = RequestDispatchService(factory, workflows)
    await workflows.register_definition(definition(1))
    await workflows.register_definition(definition(2))

    await service.configure_binding(project.id, "delivery", 1)
    first = await service.dispatch(project.id, "First")
    await service.configure_binding(project.id, "delivery", 2)
    second = await service.dispatch(project.id, "Second")

    assert first.workflow.snapshot.definition_version == 1
    assert second.workflow.snapshot.definition_version == 2


async def test_dispatch_requires_binding_and_exact_definition() -> None:
    store = MemoryStore()
    project = Project(
        key="unbound-project",
        name="Unbound Project",
        repository_url="https://example.com/unbound.git",
    )
    store.projects[project.id] = project
    service = RequestDispatchService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(ResourceConflict, match="not configured"):
        await service.dispatch(project.id, "Cannot start")
    with pytest.raises(ResourceNotFound, match="delivery@1"):
        await service.configure_binding(project.id, "delivery", 1)
