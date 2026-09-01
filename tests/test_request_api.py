from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService
from tests.support import MemoryStore, MemoryUnitOfWork


def build_app():  # type: ignore[no-untyped-def]
    store = MemoryStore()
    service = OrchestrationService(lambda: MemoryUnitOfWork(store))
    return create_app(service)


async def test_project_request_and_run_api_lifecycle() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        project_response = await client.post(
            "/v1/projects",
            json={
                "key": "jb-orchestrator",
                "name": "JB Orchestrator",
                "repository_url": "https://github.com/example/jb-orchestrator.git",
                "default_branch": "develop",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        request_response = await client.post(
            f"/v1/projects/{project_id}/requests",
            json={"title": "First", "prompt": "Build it"},
        )
        assert request_response.status_code == 201
        payload = request_response.json()
        assert payload["request"]["status"] == "active"
        assert payload["run"]["status"] == "queued"

        cancel_response = await client.post(f"/v1/runs/{payload['run']['id']}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"


async def test_api_returns_problem_detail_for_missing_resource() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        response = await client.get("/v1/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["title"] == "Resource not found"


async def test_api_returns_conflict_for_duplicate_project() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        payload = {
            "key": "jb-orchestrator",
            "name": "JB Orchestrator",
            "repository_url": "https://github.com/example/jb-orchestrator.git",
        }
        assert (await client.post("/v1/projects", json=payload)).status_code == 201
        response = await client.post("/v1/projects", json=payload)

    assert response.status_code == 409
    assert response.json()["title"] == "Resource conflict"
