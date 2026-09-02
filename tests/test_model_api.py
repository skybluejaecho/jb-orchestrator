from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    ModelCatalogService,
    OrchestrationService,
    SkillCatalogService,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_model_catalog_registers_versions_and_lists_latest() -> None:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    app = create_app(
        OrchestrationService(unit_of_work_factory),
        SkillCatalogService(unit_of_work_factory),
        ModelCatalogService(unit_of_work_factory),
    )
    payload = {
        "key": "codex-balanced",
        "name": "Codex Balanced",
        "provider": "openai",
        "model_id": "gpt-codex",
        "tier": "balanced",
        "context_window": 128000,
        "input_cost_per_million": "1.25",
        "output_cost_per_million": "5.00",
        "capabilities": ["coding", "tool-use"],
        "executor_keys": ["codex"],
        "metadata": {"reasoning": "medium"},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for version in (1, 2):
            response = await client.post("/v1/models", json={**payload, "version": version})
            assert response.status_code == 201

        latest = await client.get("/v1/models")
        exact = await client.get("/v1/models/codex-balanced", params={"version": 1})
        duplicate = await client.post("/v1/models", json={**payload, "version": 2})

    assert latest.status_code == 200
    assert latest.json()[0]["version"] == 2
    assert exact.status_code == 200
    assert exact.json()["input_cost_per_million"] == "1.25"
    assert duplicate.status_code == 409
    assert [event.event_type for event in store.events] == [
        "model.registered",
        "model.registered",
    ]
