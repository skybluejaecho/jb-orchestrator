"""Stdio entry point for the jb-orchestrator MCP server."""

from jb_orchestrator.mcp_server.client import ControlPlaneClient
from jb_orchestrator.mcp_server.server import create_server


def main() -> None:
    """Run the local stdio MCP adapter."""

    client = ControlPlaneClient.from_settings()
    if not client.authenticated:
        raise RuntimeError("JB_API_TOKEN must be configured before starting jb-mcp")
    create_server(client).run(transport="stdio")


if __name__ == "__main__":
    main()
