"""Subprocess-level readiness probe for the stdio MCP runtime."""

import os
import sys
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

from jb_orchestrator.config import Settings, get_settings
from jb_orchestrator.mcp_server.client import ControlPlaneError


@dataclass(frozen=True, slots=True)
class McpRuntimeProbeResult:
    server_name: str
    server_version: str
    tools: tuple[str, ...]
    project: dict[str, Any]


async def probe_runtime(
    project_id: UUID,
    *,
    settings: Settings | None = None,
    server_parameters: StdioServerParameters | None = None,
    timeout_seconds: float = 15.0,
) -> McpRuntimeProbeResult:
    """Launch jb-mcp and verify protocol initialization plus an authorized API call."""

    settings = settings or get_settings()
    if server_parameters is None:
        if settings.api_token is None:
            raise ControlPlaneError("JB_API_TOKEN is required by the MCP runtime probe")
        child_environment = dict(os.environ)
        child_environment.update(
            {
                "JB_CONTROL_PLANE_URL": settings.control_plane_url,
                "JB_API_TOKEN": settings.api_token.get_secret_value(),
            }
        )
        server_parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "jb_orchestrator.mcp_server.main"],
            env=child_environment,
        )

    try:
        with anyio.fail_after(timeout_seconds):
            async with (
                stdio_client(server_parameters) as (reader, writer),
                ClientSession(reader, writer) as session,
            ):
                initialized = await session.initialize()
                tools = await session.list_tools()
                project_result = await session.call_tool(
                    "get_project", arguments={"project_id": str(project_id)}
                )
    except ControlPlaneError:
        raise
    except Exception as exc:
        raise ControlPlaneError(f"MCP runtime probe failed: {exc}") from None

    if project_result.isError:
        message = " ".join(
            block.text for block in project_result.content if isinstance(block, TextContent)
        )
        raise ControlPlaneError(f"MCP get_project tool failed: {message or 'unknown error'}")
    if not isinstance(project_result.structuredContent, dict):
        raise ControlPlaneError("MCP get_project tool returned no structured content")

    return McpRuntimeProbeResult(
        server_name=initialized.serverInfo.name,
        server_version=initialized.serverInfo.version,
        tools=tuple(sorted(tool.name for tool in tools.tools)),
        project=project_result.structuredContent,
    )
