from uuid import uuid4

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from jb_orchestrator.api.event_streams import project_event_stream
from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    CreateUserRequest,
    OrchestrationService,
    ProjectObservationService,
    RegisterProject,
    WorkflowService,
)
from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.domain import Project, RequestStatus, RunStatus
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def connected_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def seed_projects(
    store: MemoryStore,
) -> tuple[OrchestrationService, ProjectObservationService, Project, Project]:
    unit_of_work_factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    orchestration = OrchestrationService(unit_of_work_factory)
    observation = ProjectObservationService(unit_of_work_factory)
    first = await orchestration.register_project(
        RegisterProject(
            key="first-project",
            name="First Project",
            repository_url="https://example.com/first.git",
        )
    )
    second = await orchestration.register_project(
        RegisterProject(
            key="second-project",
            name="Second Project",
            repository_url="https://example.com/second.git",
        )
    )
    return orchestration, observation, first, second


async def test_project_observation_lists_only_related_state() -> None:
    store = MemoryStore()
    orchestration, observation, first, second = await seed_projects(store)
    first_created = await orchestration.create_request(
        CreateUserRequest(project_id=first.id, prompt="Build first")
    )
    await orchestration.create_request(
        CreateUserRequest(project_id=second.id, prompt="Build second")
    )

    projects = await observation.list_projects(limit=1)
    requests = await observation.list_requests(first.id, status=RequestStatus.ACTIVE)
    runs = await observation.list_runs(first_created.request.id, status=RunStatus.QUEUED)
    events = await observation.list_events(first.id)

    assert len(projects) == 1
    assert [item.id for item in requests] == [first_created.request.id]
    assert [item.id for item in runs] == [first_created.run.id]
    assert [event.event_type for event in events] == [
        "project.registered",
        "request.created",
    ]
    assert all(event.aggregate_id != second.id for event in events)


async def test_project_event_cursor_resumes_and_rejects_unknown_values() -> None:
    store = MemoryStore()
    orchestration, observation, first, _ = await seed_projects(store)
    await orchestration.create_request(
        CreateUserRequest(project_id=first.id, prompt="Observe this")
    )
    events = await observation.list_events(first.id)

    resumed = await observation.list_events(first.id, after_event_id=events[0].id)

    assert [event.event_type for event in resumed] == ["request.created"]
    with pytest.raises(ResourceNotFound):
        await observation.list_events(first.id, after_event_id=uuid4())


async def test_project_event_stream_replays_project_event() -> None:
    store = MemoryStore()
    _, observation, first, _ = await seed_projects(store)
    events = await observation.list_events(first.id)
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": []},
        receive=connected_receive,
    )
    stream = project_event_stream(
        request=request,
        service=observation,
        project_id=first.id,
        initial_events=events,
        cursor=None,
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=1,
    )

    message = await anext(stream)
    await stream.aclose()

    assert f"id: {events[0].id}" in message
    assert '"aggregate_type":"project"' in message


async def test_project_observation_api_lists_state_and_validates_cursor() -> None:
    store = MemoryStore()
    orchestration, observation, first, _ = await seed_projects(store)
    created = await orchestration.create_request(
        CreateUserRequest(project_id=first.id, prompt="Show in Jarvis")
    )
    workflow_service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await workflow_service.register_definition(
        WorkflowDefinition(
            key="observation-flow",
            version=1,
            entry_node="approval",
            nodes=(
                NodeDefinition(key="approval", kind=NodeKind.APPROVAL),
                NodeDefinition(
                    key="done",
                    kind=NodeKind.TERMINAL,
                    terminal_status=WorkflowStatus.SUCCEEDED,
                ),
                NodeDefinition(
                    key="rejected",
                    kind=NodeKind.TERMINAL,
                    terminal_status=WorkflowStatus.FAILED,
                ),
            ),
            edges=(
                EdgeDefinition(source="approval", outcome=NodeOutcome.APPROVED, target="done"),
                EdgeDefinition(source="approval", outcome=NodeOutcome.REJECTED, target="rejected"),
            ),
        )
    )
    execution = await workflow_service.start(created.run.id, "observation-flow")
    app = create_app(
        service=orchestration,
        workflow_service=workflow_service,
        project_observation_service=observation,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projects = await client.get("/v1/projects")
        requests = await client.get(
            f"/v1/projects/{first.id}/requests", params={"status": "active"}
        )
        runs = await client.get(f"/v1/requests/{created.request.id}/runs")
        workflows = await client.get(
            f"/v1/projects/{first.id}/workflow-executions",
            params={"status": "awaiting_approval"},
        )
        unknown_cursor = await client.get(
            f"/v1/projects/{first.id}/events/stream", params={"after": str(uuid4())}
        )

    assert projects.status_code == 200
    assert len(projects.json()) == 2
    assert [item["id"] for item in requests.json()] == [str(created.request.id)]
    assert [item["id"] for item in runs.json()] == [str(created.run.id)]
    assert [item["id"] for item in workflows.json()] == [str(execution.id)]
    assert workflows.json()[0]["nodes"][0]["status"] == "awaiting_approval"
    assert unknown_cursor.status_code == 404
