from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, SkillCatalogService
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_skill_catalog_registers_versions_and_lists_latest() -> None:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    app = create_app(
        OrchestrationService(unit_of_work_factory),
        SkillCatalogService(unit_of_work_factory),
    )
    transport = ASGITransport(app=app)
    digest = "sha256:" + "a" * 64
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for version in (1, 2):
            response = await client.post(
                "/v1/skills",
                json={
                    "key": "code-review",
                    "version": version,
                    "name": "Code Review",
                    "description": "Review changes without modifying them.",
                    "source_kind": "git",
                    "source_uri": "https://example.com/skills.git",
                    "content_digest": digest,
                    "source_revision": "abc123",
                    "metadata": {"license": "MIT"},
                },
            )
            assert response.status_code == 201

        latest = await client.get("/v1/skills")
        exact = await client.get("/v1/skills/code-review", params={"version": 1})
        duplicate = await client.post(
            "/v1/skills",
            json={
                "key": "code-review",
                "version": 2,
                "name": "Code Review",
                "description": "Duplicate",
                "source_kind": "git",
                "source_uri": "https://example.com/skills.git",
                "content_digest": digest,
                "source_revision": "abc123",
            },
        )

    assert latest.status_code == 200
    assert latest.json()[0]["version"] == 2
    assert exact.status_code == 200
    assert exact.json()["version"] == 1
    assert duplicate.status_code == 409
    assert [event.event_type for event in store.events] == [
        "skill.registered",
        "skill.registered",
    ]
