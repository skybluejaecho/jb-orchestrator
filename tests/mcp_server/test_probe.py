import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from pydantic import SecretStr

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, SecurityService
from jb_orchestrator.config import Settings
from jb_orchestrator.domain import Project
from jb_orchestrator.mcp_server import probe_runtime
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


@asynccontextmanager
async def serve_api(app: object) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        if not server.started:
            raise RuntimeError("test API did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
        listener.close()


async def test_probe_launches_real_stdio_process_and_calls_authenticated_api() -> None:
    store = MemoryStore()
    unit_of_work = lambda: MemoryUnitOfWork(store)  # noqa: E731
    project = Project(
        key="runtime-probe",
        name="Runtime Probe",
        repository_url="https://example.test/runtime-probe.git",
    )
    store.projects[project.id] = project
    security = SecurityService(unit_of_work)
    issued = await security.issue(
        key="runtime-probe-client",
        name="Runtime Probe Client",
        permissions={ApiPermission.PROJECT_READ},
        project_ids={project.id},
    )
    api = create_app(
        service=OrchestrationService(unit_of_work),
        security_service=security,
        auth_enabled=True,
    )

    async with serve_api(api) as control_plane_url:
        result = await probe_runtime(
            project.id,
            settings=Settings(
                control_plane_url=control_plane_url,
                api_token=SecretStr(issued.token),
            ),
        )

    assert result.server_name == "jb-orchestrator"
    assert result.project["id"] == str(project.id)
    assert result.project["key"] == "runtime-probe"
    assert "dispatch_request" in result.tools
    assert "get_project" in result.tools
