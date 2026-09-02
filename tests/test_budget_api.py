from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import (
    BudgetService,
    ModelCatalogService,
    OrchestrationService,
    RegisterProject,
    SkillCatalogService,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_project_budget_can_be_configured_and_read() -> None:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    orchestration = OrchestrationService(unit_of_work_factory)
    project = await orchestration.register_project(
        RegisterProject(
            key="budget-api",
            name="Budget API",
            repository_url="https://example.com/repository.git",
            default_branch="main",
        )
    )
    app = create_app(
        orchestration,
        SkillCatalogService(unit_of_work_factory),
        ModelCatalogService(unit_of_work_factory),
        BudgetService(unit_of_work_factory),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        configured = await client.put(
            f"/v1/projects/{project.id}/budget", json={"limit_usd": "5.00"}
        )
        fetched = await client.get(f"/v1/projects/{project.id}/budget")
        usage = await client.get(f"/v1/projects/{project.id}/usage")

    assert configured.status_code == 200
    assert configured.json()["limit_usd"] == "5.000000"
    assert configured.json()["available_usd"] == "5.000000"
    assert fetched.json() == configured.json()
    assert usage.json() == []
