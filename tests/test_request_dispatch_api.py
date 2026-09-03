from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    OrchestrationService,
    RequestDispatchService,
    WorkflowService,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_project_binding_and_one_call_dispatch_api() -> None:
    store = MemoryStore()
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflow_service = WorkflowService(factory)
    app = create_app(
        service=OrchestrationService(factory),
        workflow_service=workflow_service,
        request_dispatch_service=RequestDispatchService(factory, workflow_service),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = await client.post(
            "/v1/projects",
            json={
                "key": "one-call-project",
                "name": "One Call",
                "repository_url": "https://example.com/one-call.git",
            },
        )
        workflow = await client.post(
            "/v1/workflows",
            json={
                "key": "delivery",
                "version": 1,
                "entry_node": "work",
                "nodes": [
                    {"key": "work", "kind": "task"},
                    {"key": "done", "kind": "terminal", "terminal_status": "succeeded"},
                ],
                "edges": [{"source": "work", "outcome": "success", "target": "done"}],
            },
        )
        project_id = project.json()["id"]
        bound = await client.put(
            f"/v1/projects/{project_id}/workflow-binding",
            json={"definition_key": "delivery", "definition_version": 1},
        )
        fetched = await client.get(f"/v1/projects/{project_id}/workflow-binding")
        dispatched = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Deliver", "prompt": "Implement this"},
            headers={"Idempotency-Key": "api-request-1"},
        )
        replayed = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Deliver", "prompt": "Implement this"},
            headers={"Idempotency-Key": "api-request-1"},
        )
        conflicting = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Different", "prompt": "Implement something else"},
            headers={"Idempotency-Key": "api-request-1"},
        )

    assert project.status_code == 201
    assert workflow.status_code == 201
    assert bound.status_code == 200
    assert fetched.json() == bound.json()
    assert dispatched.status_code == 201
    assert dispatched.json()["request"]["status"] == "active"
    assert dispatched.json()["run"]["status"] == "running"
    assert dispatched.json()["workflow"]["definition_version"] == 1
    assert dispatched.json()["workflow"]["request_context"]["prompt"] == "Implement this"
    assert dispatched.json()["replayed"] is False
    assert replayed.status_code == 201
    assert replayed.json()["replayed"] is True
    assert replayed.json()["workflow"]["id"] == dispatched.json()["workflow"]["id"]
    assert conflicting.status_code == 409


async def test_dispatch_api_requires_idempotency_key() -> None:
    store = MemoryStore()
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflow_service = WorkflowService(factory)
    app = create_app(
        service=OrchestrationService(factory),
        workflow_service=workflow_service,
        request_dispatch_service=RequestDispatchService(factory, workflow_service),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/projects/00000000-0000-0000-0000-000000000000/dispatches",
            json={"prompt": "Missing key"},
        )

    assert response.status_code == 422
