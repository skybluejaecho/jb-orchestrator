"""MCP tool declarations backed by the authenticated control-plane API."""

from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from jb_orchestrator.mcp_server.client import ControlPlaneClient

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
DISPATCH = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
APPROVAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
CANCELLATION = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)


def create_server(client: ControlPlaneClient | None = None) -> FastMCP[None]:
    """Create a stdio MCP adapter; the control plane remains the source of truth."""

    control_plane = client or ControlPlaneClient.from_settings()
    server: FastMCP[None] = FastMCP(
        "jb-orchestrator",
        instructions=(
            "Use these tools to dispatch and observe jb-orchestrator workflows. "
            "Reuse the same idempotency key when retrying a dispatch. Ask the user before "
            "approval or cancellation when their intent is not already explicit."
        ),
    )

    @server.tool(annotations=READ_ONLY)
    async def get_project(project_id: UUID) -> dict[str, Any]:
        """Get one authorized project by its UUID."""

        return await control_plane.get_project(project_id)

    @server.tool(annotations=READ_ONLY)
    async def list_project_requests(
        project_id: UUID,
        status: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> list[Any]:
        """List recent requests in one authorized project."""

        return await control_plane.list_project_requests(project_id, status=status, limit=limit)

    @server.tool(annotations=READ_ONLY)
    async def list_project_workflows(
        project_id: UUID,
        status: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> list[Any]:
        """List recent workflow executions in one authorized project."""

        return await control_plane.list_project_workflows(project_id, status=status, limit=limit)

    @server.tool(annotations=DISPATCH)
    async def dispatch_request(
        project_id: UUID,
        prompt: Annotated[str, Field(min_length=1)],
        idempotency_key: Annotated[str, Field(min_length=1, max_length=128)],
        title: Annotated[str | None, Field(max_length=255)] = None,
        external_request_id: Annotated[str | None, Field(max_length=255)] = None,
        actor_id: Annotated[str | None, Field(max_length=255)] = None,
        conversation_id: Annotated[str | None, Field(max_length=512)] = None,
    ) -> dict[str, Any]:
        """Start the project's bound workflow; reuse the key for an exact retry."""

        return await control_plane.dispatch_request(
            project_id,
            prompt=prompt,
            idempotency_key=idempotency_key,
            title=title,
            external_request_id=external_request_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )

    @server.tool(annotations=READ_ONLY)
    async def get_request(request_id: UUID) -> dict[str, Any]:
        """Get one request and its durable status."""

        return await control_plane.get_request(request_id)

    @server.tool(annotations=READ_ONLY)
    async def get_run(run_id: UUID) -> dict[str, Any]:
        """Get one run and its durable status."""

        return await control_plane.get_run(run_id)

    @server.tool(annotations=READ_ONLY)
    async def get_workflow_execution(execution_id: UUID) -> dict[str, Any]:
        """Get node-level state for one workflow execution."""

        return await control_plane.get_workflow_execution(execution_id)

    @server.tool(annotations=READ_ONLY)
    async def list_artifacts(execution_id: UUID) -> list[Any]:
        """List immutable artifacts produced by workflow nodes."""

        return await control_plane.list_artifacts(execution_id)

    @server.tool(annotations=APPROVAL)
    async def approve_workflow_node(
        execution_id: UUID,
        node_key: Annotated[str, Field(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        """Approve a workflow node that is waiting at a human gate."""

        return await control_plane.approve_workflow_node(execution_id, node_key)

    @server.tool(annotations=CANCELLATION)
    async def cancel_run(run_id: UUID) -> dict[str, Any]:
        """Cancel an active run and its request hierarchy."""

        return await control_plane.cancel_run(run_id)

    return server
