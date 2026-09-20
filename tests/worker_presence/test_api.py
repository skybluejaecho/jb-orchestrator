from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import WorkerPresenceService
from jb_orchestrator.worker_presence import WorkerKind
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_worker_presence_api_reports_derived_stale_status() -> None:
    store = MemoryStore()
    service = WorkerPresenceService(lambda: MemoryUnitOfWork(store))
    worker = await service.register(
        worker_id="workspace-a",
        kind=WorkerKind.WORKSPACE,
        hostname="host-a",
        process_id=42,
        capabilities=("inspect", "cleanup"),
        workspace_scope="git-worktree:scope-a",
    )
    worker.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
    app = create_app(worker_presence_service=service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/workers")

    assert response.status_code == 200
    [payload] = response.json()
    assert payload["worker_id"] == "workspace-a"
    assert payload["kind"] == "workspace"
    assert payload["observed_status"] == "stale"
    assert payload["capabilities"] == ["cleanup", "inspect"]
