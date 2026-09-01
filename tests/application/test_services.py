from uuid import uuid4

import pytest

from jb_orchestrator.application import CreateUserRequest, OrchestrationService, RegisterProject
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import InvalidStateTransition, RequestStatus, RunStatus
from tests.support import MemoryStore, MemoryUnitOfWork


def build_service(store: MemoryStore) -> OrchestrationService:
    return OrchestrationService(lambda: MemoryUnitOfWork(store))


async def test_register_project_rejects_duplicate_key() -> None:
    store = MemoryStore()
    service = build_service(store)
    command = RegisterProject(
        key="jb-orchestrator",
        name="JB Orchestrator",
        repository_url="https://github.com/example/jb-orchestrator.git",
    )
    await service.register_project(command)

    with pytest.raises(ResourceConflict, match="already exists"):
        await service.register_project(command)


async def test_create_request_persists_active_request_and_queued_run() -> None:
    store = MemoryStore()
    service = build_service(store)
    project = await service.register_project(
        RegisterProject(
            key="jb-orchestrator",
            name="JB Orchestrator",
            repository_url="https://github.com/example/jb-orchestrator.git",
        )
    )

    created = await service.create_request(
        CreateUserRequest(project_id=project.id, title="First", prompt="Build it")
    )

    assert created.request.status is RequestStatus.ACTIVE
    assert created.run.status is RunStatus.QUEUED
    assert created.run.request_id == created.request.id
    assert store.requests[created.request.id] is created.request
    assert store.runs[created.run.id] is created.run
    assert [event.event_type for event in store.events] == [
        "project.registered",
        "request.created",
    ]


async def test_cancel_run_cancels_request_in_same_use_case() -> None:
    store = MemoryStore()
    service = build_service(store)
    project = await service.register_project(
        RegisterProject(
            key="jb-orchestrator",
            name="JB Orchestrator",
            repository_url="https://github.com/example/jb-orchestrator.git",
        )
    )
    created = await service.create_request(
        CreateUserRequest(project_id=project.id, prompt="Build it")
    )

    cancelled = await service.cancel_run(created.run.id)

    assert cancelled.status is RunStatus.CANCELLED
    assert store.requests[created.request.id].status is RequestStatus.CANCELLED
    assert store.events[-1].event_type == "run.cancelled"


async def test_approve_requires_awaiting_approval_state() -> None:
    store = MemoryStore()
    service = build_service(store)
    project = await service.register_project(
        RegisterProject(
            key="jb-orchestrator",
            name="JB Orchestrator",
            repository_url="https://github.com/example/jb-orchestrator.git",
        )
    )
    created = await service.create_request(
        CreateUserRequest(project_id=project.id, prompt="Build it")
    )

    with pytest.raises(InvalidStateTransition):
        await service.approve_run(created.run.id)

    created.run.transition_to(RunStatus.PLANNING)
    created.run.transition_to(RunStatus.AWAITING_APPROVAL)
    approved = await service.approve_run(created.run.id)
    assert approved.status is RunStatus.READY


async def test_missing_project_is_reported() -> None:
    service = build_service(MemoryStore())

    with pytest.raises(ResourceNotFound, match="project"):
        await service.get_project(uuid4())
