from typing import Any, cast
from uuid import UUID, uuid4

from jb_orchestrator.mcp_server import create_server


class StubControlPlaneClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_project(self, project_id: UUID) -> dict[str, Any]:
        self.calls.append(("get_project", project_id))
        return {"id": str(project_id), "key": "alpha"}

    async def list_project_requests(
        self, project_id: UUID, *, status: str | None = None, limit: int = 20
    ) -> list[Any]:
        return []

    async def list_project_workflows(
        self, project_id: UUID, *, status: str | None = None, limit: int = 20
    ) -> list[Any]:
        return []

    async def list_workflow_options(self, project_id: UUID) -> dict[str, Any]:
        return {"project_id": str(project_id), "default": None, "workflows": []}

    async def dispatch_request(self, project_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return {"project_id": str(project_id), **kwargs}

    async def get_request(self, request_id: UUID) -> dict[str, Any]:
        return {"id": str(request_id)}

    async def get_run(self, run_id: UUID) -> dict[str, Any]:
        return {"id": str(run_id)}

    async def get_workflow_execution(self, execution_id: UUID) -> dict[str, Any]:
        return {"id": str(execution_id)}

    async def list_artifacts(self, execution_id: UUID) -> list[Any]:
        return []

    async def approve_workflow_node(self, execution_id: UUID, node_key: str) -> dict[str, Any]:
        return {"id": str(execution_id), "node_key": node_key}

    async def cancel_run(self, run_id: UUID) -> dict[str, Any]:
        return {"id": str(run_id), "status": "cancelled"}


async def test_server_exposes_bounded_tools_with_safety_annotations() -> None:
    server = create_server(StubControlPlaneClient())  # type: ignore[arg-type]

    tools = {tool.name: tool for tool in await server.list_tools()}

    assert set(tools) == {
        "get_project",
        "list_project_requests",
        "list_project_workflows",
        "list_workflow_options",
        "dispatch_request",
        "get_request",
        "get_run",
        "get_workflow_execution",
        "list_artifacts",
        "approve_workflow_node",
        "cancel_run",
    }
    assert tools["get_run"].annotations is not None
    assert tools["get_run"].annotations.readOnlyHint is True
    assert tools["dispatch_request"].annotations is not None
    assert tools["dispatch_request"].annotations.idempotentHint is True
    assert tools["cancel_run"].annotations is not None
    assert tools["cancel_run"].annotations.destructiveHint is True


async def test_tool_call_delegates_to_control_plane_client() -> None:
    client = StubControlPlaneClient()
    server = create_server(client)  # type: ignore[arg-type]
    project_id = uuid4()

    result = await server.call_tool("get_project", {"project_id": str(project_id)})

    assert client.calls == [("get_project", project_id)]
    _, structured = cast(tuple[Any, dict[str, Any]], result)
    assert structured["id"] == str(project_id)


async def test_dispatch_tool_accepts_exact_node_skill_addons() -> None:
    server = create_server(StubControlPlaneClient())  # type: ignore[arg-type]
    project_id = uuid4()

    result = await server.call_tool(
        "dispatch_request",
        {
            "project_id": str(project_id),
            "prompt": "Review it",
            "idempotency_key": "skill-addon-1",
            "skill_addons": [
                {
                    "node_key": "verify",
                    "skills": [{"key": "security-review", "version": 2}],
                }
            ],
        },
    )

    _, structured = cast(tuple[Any, dict[str, Any]], result)
    assert structured["skill_addons"] == [
        {
            "node_key": "verify",
            "skills": [{"key": "security-review", "version": 2}],
        }
    ]
