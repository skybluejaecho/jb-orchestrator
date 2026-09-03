from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, WorkflowService
from tests.support import MemoryStore, MemoryUnitOfWork


def workflow_payload(*, version: int = 1) -> dict[str, object]:
    return {
        "key": "approval-flow",
        "version": version,
        "entry_node": "approval",
        "nodes": [
            {"key": "approval", "kind": "approval"},
            {
                "key": "accepted",
                "kind": "terminal",
                "terminal_status": "succeeded",
            },
            {
                "key": "rejected",
                "kind": "terminal",
                "terminal_status": "failed",
            },
        ],
        "edges": [
            {"source": "approval", "outcome": "approved", "target": "accepted"},
            {"source": "approval", "outcome": "rejected", "target": "rejected"},
        ],
    }


def build_app() -> tuple[FastAPI, MemoryStore]:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    app = create_app(
        service=OrchestrationService(unit_of_work_factory),
        workflow_service=WorkflowService(unit_of_work_factory),
    )
    return app, store


async def create_run(client: AsyncClient) -> str:
    project_response = await client.post(
        "/v1/projects",
        json={
            "key": "workflow-project",
            "name": "Workflow Project",
            "repository_url": "https://github.com/example/workflow-project.git",
        },
    )
    project_id = project_response.json()["id"]
    request_response = await client.post(
        f"/v1/projects/{project_id}/requests",
        json={"prompt": "Run the workflow"},
    )
    return str(request_response.json()["run"]["id"])


async def test_workflow_control_api_registration_execution_and_approval() -> None:
    app, store = build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run_id = await create_run(client)
        first = await client.post("/v1/workflows", json=workflow_payload(version=1))
        latest = await client.post("/v1/workflows", json=workflow_payload(version=2))
        definitions = await client.get("/v1/workflows")
        exact = await client.get("/v1/workflows/approval-flow", params={"version": 1})

        started = await client.post(
            f"/v1/runs/{run_id}/workflow",
            json={"definition_key": "approval-flow", "version": 1},
        )
        execution_id = started.json()["id"]
        by_run = await client.get(f"/v1/runs/{run_id}/workflow")
        by_execution = await client.get(f"/v1/workflow-executions/{execution_id}")
        artifacts = await client.get(f"/v1/workflow-executions/{execution_id}/artifacts")
        approved = await client.post(
            f"/v1/workflow-executions/{execution_id}/approvals/approval",
            json={"approved": True},
        )

    assert first.status_code == 201
    assert latest.status_code == 201
    assert definitions.status_code == 200
    assert [(item["key"], item["version"]) for item in definitions.json()] == [("approval-flow", 2)]
    assert exact.status_code == 200
    assert exact.json()["version"] == 1
    assert started.status_code == 201
    assert started.json()["status"] == "awaiting_approval"
    assert started.json()["definition_version"] == 1
    assert started.json()["request_context"]["prompt"] == "Run the workflow"
    assert started.json()["request_context"]["project_key"] == "workflow-project"
    assert by_run.json()["id"] == execution_id
    assert by_execution.json()["nodes"][0]["status"] == "awaiting_approval"
    assert artifacts.status_code == 200
    assert artifacts.json() == []
    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
    assert approved.json()["nodes"][0]["outcome"] == "approved"
    assert [event.event_type for event in store.events][-4:] == [
        "workflow.definition_registered",
        "workflow.definition_registered",
        "workflow.started",
        "workflow.approval_resolved",
    ]


async def test_workflow_control_api_conflicts_validation_and_cancellation() -> None:
    app, _ = build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run_id = await create_run(client)
        assert (await client.post("/v1/workflows", json=workflow_payload())).status_code == 201
        duplicate = await client.post("/v1/workflows", json=workflow_payload())
        invalid_payload = workflow_payload()
        invalid_payload["key"] = "invalid-flow"
        invalid_payload["edges"] = [
            {"source": "approval", "outcome": "approved", "target": "missing"},
            {"source": "approval", "outcome": "rejected", "target": "rejected"},
        ]
        invalid = await client.post("/v1/workflows", json=invalid_payload)
        started = await client.post(
            f"/v1/runs/{run_id}/workflow",
            json={"definition_key": "approval-flow"},
        )
        cancelled = await client.post(f"/v1/workflow-executions/{started.json()['id']}/cancel")
        missing = await client.get("/v1/workflows/missing")

    assert duplicate.status_code == 409
    assert invalid.status_code == 422
    assert invalid.json()["title"] == "Workflow definition validation failed"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert [node["status"] for node in cancelled.json()["nodes"]] == [
        "cancelled",
        "pending",
        "pending",
    ]
    assert missing.status_code == 404


async def test_workflow_api_accepts_explicit_parallel_fork_and_join() -> None:
    app, _ = build_app()
    payload = {
        "key": "parallel-flow",
        "version": 1,
        "entry_node": "fork",
        "nodes": [
            {"key": "fork", "kind": "fork"},
            {"key": "research", "kind": "task"},
            {"key": "design", "kind": "task"},
            {"key": "join", "kind": "join"},
            {"key": "done", "kind": "terminal", "terminal_status": "succeeded"},
        ],
        "edges": [
            {"source": "fork", "outcome": "success", "target": "research"},
            {"source": "fork", "outcome": "success", "target": "design"},
            {"source": "research", "outcome": "success", "target": "join"},
            {"source": "design", "outcome": "success", "target": "join"},
            {"source": "join", "outcome": "success", "target": "done"},
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        registered = await client.post("/v1/workflows", json=payload)
        run_id = await create_run(client)
        started = await client.post(
            f"/v1/runs/{run_id}/workflow",
            json={"definition_key": "parallel-flow"},
        )

    assert registered.status_code == 201
    assert [node["kind"] for node in registered.json()["nodes"]] == [
        "fork",
        "task",
        "task",
        "join",
        "terminal",
    ]
    statuses = {node["node_key"]: node["status"] for node in started.json()["nodes"]}
    assert started.status_code == 201
    assert statuses == {
        "fork": "succeeded",
        "research": "ready",
        "design": "ready",
        "join": "pending",
        "done": "pending",
    }
