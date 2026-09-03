from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, PhasePackCatalogService
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_phase_pack_catalog_registers_versions_and_lists_latest() -> None:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    app = create_app(
        OrchestrationService(unit_of_work_factory),
        phase_pack_service=PhasePackCatalogService(unit_of_work_factory),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for version in (1, 2):
            response = await client.post(
                "/v1/phase-packs",
                json={
                    "key": "implementation",
                    "version": version,
                    "name": "Implementation",
                    "description": "Implement an approved plan.",
                    "instructions": "Apply changes and verify them.",
                    "inputs": [
                        {
                            "key": "approved_plan",
                            "description": "The approved implementation plan.",
                        }
                    ],
                    "output_contract": {"required": ["summary", "tests"]},
                },
            )
            assert response.status_code == 201

        latest = await client.get("/v1/phase-packs")
        exact = await client.get("/v1/phase-packs/implementation", params={"version": 1})

    assert latest.status_code == 200
    assert latest.json()[0]["version"] == 2
    assert exact.status_code == 200
    assert exact.json()["inputs"][0]["key"] == "approved_plan"
    assert [event.event_type for event in store.events] == [
        "phase_pack.registered",
        "phase_pack.registered",
    ]
