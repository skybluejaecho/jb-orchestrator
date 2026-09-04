from uuid import UUID

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    OrchestrationService,
    RequestDispatchService,
    SkillCatalogService,
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
        skill_service=SkillCatalogService(factory),
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
        skill = await client.post(
            "/v1/skills",
            json={
                "key": "security-review",
                "version": 1,
                "name": "Security Review",
                "description": "Review security boundaries",
                "source_kind": "local",
                "source_uri": "security-review",
                "content_digest": f"sha256:{'d' * 64}",
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
        options = await client.get(f"/v1/projects/{project_id}/workflow-options")
        dispatched = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Deliver", "prompt": "Implement this"},
            headers={
                "Idempotency-Key": "api-request-1",
                "X-JB-Ingress-Key": "openclaw",
                "X-JB-External-Request-ID": "telegram-message-42",
                "X-JB-Actor-ID": "telegram:user-7",
                "X-JB-Conversation-ID": "telegram:chat-3",
            },
        )
        replayed = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Deliver", "prompt": "Implement this"},
            headers={
                "Idempotency-Key": "api-request-1",
                "X-JB-Ingress-Key": "openclaw",
                "X-JB-External-Request-ID": "telegram-message-42",
                "X-JB-Actor-ID": "telegram:user-7",
                "X-JB-Conversation-ID": "telegram:chat-3",
            },
        )
        conflicting = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Different", "prompt": "Implement something else"},
            headers={
                "Idempotency-Key": "api-request-1",
                "X-JB-Ingress-Key": "openclaw",
                "X-JB-External-Request-ID": "telegram-message-42",
                "X-JB-Actor-ID": "telegram:user-7",
                "X-JB-Conversation-ID": "telegram:chat-3",
            },
        )
        other_ingress = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={"title": "Jarvis", "prompt": "A separate request"},
            headers={
                "Idempotency-Key": "api-request-1",
                "X-JB-Ingress-Key": "jarvis",
            },
        )
        overridden = await client.post(
            f"/v1/projects/{project_id}/dispatches",
            json={
                "title": "Selected",
                "prompt": "Use the selected workflow",
                "workflow": {
                    "definition_key": "delivery",
                    "definition_version": 1,
                },
                "skill_addons": [
                    {
                        "node_key": "work",
                        "skills": [{"key": "security-review", "version": 1}],
                    }
                ],
            },
            headers={"Idempotency-Key": "api-request-override"},
        )

    assert project.status_code == 201
    assert skill.status_code == 201
    assert workflow.status_code == 201
    assert bound.status_code == 200
    assert fetched.json() == bound.json()
    assert options.status_code == 200
    assert options.json()["default"] == bound.json()
    assert [(item["key"], item["version"]) for item in options.json()["workflows"]] == [
        ("delivery", 1)
    ]
    [workflow_option] = options.json()["workflows"]
    assert options.json()["default_workflow"] == workflow_option
    assert workflow_option["entry_node"] == "work"
    assert [node["key"] for node in workflow_option["nodes"]] == ["work", "done"]
    assert workflow_option["edges"] == [
        {"source": "work", "outcome": "success", "target": "done", "condition": None}
    ]
    assert workflow_option["phase_packs"] == []
    assert workflow_option["skills"] == []
    assert options.json()["available_skills"] == [
        {
            "key": "security-review",
            "version": 1,
            "name": "Security Review",
            "description": "Review security boundaries",
            "source_kind": "local",
        }
    ]
    assert dispatched.status_code == 201
    assert dispatched.json()["request"]["status"] == "active"
    assert dispatched.json()["request"]["origin"] == {
        "ingress_key": "openclaw",
        "external_request_id": "telegram-message-42",
        "actor_id": "telegram:user-7",
        "conversation_id": "telegram:chat-3",
    }
    assert dispatched.json()["run"]["status"] == "running"
    assert dispatched.json()["workflow"]["definition_version"] == 1
    assert dispatched.json()["workflow"]["request_context"]["prompt"] == "Implement this"
    assert dispatched.json()["replayed"] is False
    assert replayed.status_code == 201
    assert replayed.json()["replayed"] is True
    assert replayed.json()["workflow"]["id"] == dispatched.json()["workflow"]["id"]
    assert conflicting.status_code == 409
    assert other_ingress.status_code == 201
    assert other_ingress.json()["request"]["origin"]["ingress_key"] == "jarvis"
    assert overridden.status_code == 201
    assert overridden.json()["workflow"]["definition_key"] == "delivery"
    overridden_execution = store.workflow_executions[UUID(overridden.json()["workflow"]["id"])]
    assert [skill.key for skill in overridden_execution.snapshot.skills] == ["security-review"]
    assert store.events[-2].payload["selection_source"] == "request_override"


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
