from typing import Any, cast

from httpx import ASGITransport
from mcp.shared.memory import create_connected_server_and_client_session

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    OrchestrationService,
    RequestDispatchService,
    SecurityService,
    WorkflowService,
)
from jb_orchestrator.domain import Project
from jb_orchestrator.mcp_server import ControlPlaneClient, create_server
from jb_orchestrator.security import ApiPermission
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_mcp_protocol_dispatches_through_authenticated_api() -> None:
    store = MemoryStore()
    unit_of_work = lambda: MemoryUnitOfWork(store)  # noqa: E731
    project = Project(
        key="mcp-e2e",
        name="MCP E2E",
        repository_url="https://example.test/mcp-e2e.git",
    )
    store.projects[project.id] = project
    workflow_service = WorkflowService(unit_of_work)
    delivery = await workflow_service.register_definition(
        WorkflowDefinition(
            key="delivery",
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
    )
    selected = await workflow_service.register_definition(
        WorkflowDefinition(
            key="planning-only",
            version=1,
            entry_node="work",
            nodes=delivery.nodes,
            edges=delivery.edges,
        )
    )
    dispatch_service = RequestDispatchService(unit_of_work, workflow_service)
    await dispatch_service.configure_binding(project.id, "delivery", 1)
    security_service = SecurityService(unit_of_work)
    account = await security_service.issue(
        key="mcp-e2e-client",
        name="MCP E2E Client",
        permissions={ApiPermission.PROJECT_READ, ApiPermission.REQUEST_DISPATCH},
        project_ids={project.id},
    )
    api = create_app(
        service=OrchestrationService(unit_of_work),
        workflow_service=workflow_service,
        request_dispatch_service=dispatch_service,
        security_service=security_service,
        auth_enabled=True,
    )
    control_plane = ControlPlaneClient(
        base_url="http://control.test",
        token=account.token,
        transport=ASGITransport(app=api),
    )
    server = create_server(control_plane)

    async with create_connected_server_and_client_session(server, raise_exceptions=True) as session:
        tool_names = {tool.name for tool in (await session.list_tools()).tools}
        project_result = await session.call_tool(
            "get_project", arguments={"project_id": str(project.id)}
        )
        options_result = await session.call_tool(
            "list_workflow_options", arguments={"project_id": str(project.id)}
        )
        dispatched = await session.call_tool(
            "dispatch_request",
            arguments={
                "project_id": str(project.id),
                "prompt": "Implement the requested feature",
                "title": "MCP integration",
                "idempotency_key": "mcp-e2e-message-1",
                "external_request_id": "openclaw-message-1",
                "actor_id": "openclaw:user-7",
                "conversation_id": "openclaw:session-3",
                "definition_key": selected.key,
                "definition_version": selected.version,
            },
        )
        replayed = await session.call_tool(
            "dispatch_request",
            arguments={
                "project_id": str(project.id),
                "prompt": "Implement the requested feature",
                "title": "MCP integration",
                "idempotency_key": "mcp-e2e-message-1",
                "external_request_id": "openclaw-message-1",
                "actor_id": "openclaw:user-7",
                "conversation_id": "openclaw:session-3",
                "definition_key": selected.key,
                "definition_version": selected.version,
            },
        )

    assert "dispatch_request" in tool_names
    assert "list_workflow_options" in tool_names
    assert project_result.isError is False
    project_payload = cast(dict[str, Any], project_result.structuredContent)
    assert project_payload["key"] == "mcp-e2e"
    options_payload = cast(dict[str, Any], options_result.structuredContent)
    assert options_payload["default"]["definition_key"] == "delivery"
    assert {(item["key"], item["version"]) for item in options_payload["workflows"]} == {
        ("delivery", 1),
        ("planning-only", 1),
    }
    dispatch_payload = cast(dict[str, Any], dispatched.structuredContent)
    replay_payload = cast(dict[str, Any], replayed.structuredContent)
    assert dispatch_payload["replayed"] is False
    assert replay_payload["replayed"] is True
    assert dispatch_payload["workflow"]["id"] == replay_payload["workflow"]["id"]
    assert dispatch_payload["workflow"]["definition_key"] == "planning-only"
    assert dispatch_payload["request"]["origin"] == {
        "ingress_key": "mcp",
        "external_request_id": "openclaw-message-1",
        "actor_id": "openclaw:user-7",
        "conversation_id": "openclaw:session-3",
    }
