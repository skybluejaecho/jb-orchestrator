from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import ExternalExecutionService, ScmPublicationService
from tests.scm.test_publication_service import managed_execution
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_publication_request_list_and_replay() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    executions = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    publications = ScmPublicationService(lambda: MemoryUnitOfWork(store))
    app = create_app(
        external_execution_service=executions,
        scm_publication_service=publications,
    )
    path = f"/v1/external-executions/{execution.id}/scm-publications"
    payload = {
        "provider_key": "github",
        "target_branch": "develop",
        "title": "Review feature",
        "body": "Please review.",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(path, headers={"Idempotency-Key": "publish-1"}, json=payload)
        repeated = await client.post(path, headers={"Idempotency-Key": "publish-1"}, json=payload)
        listed = await client.get(path)
        invalid = await client.post(
            path,
            headers={"Idempotency-Key": "publish-2"},
            json={**payload, "provider_key": "GitHub"},
        )

    assert first.status_code == 202
    assert repeated.status_code == 200
    assert first.json()["id"] == repeated.json()["id"]
    assert first.json()["repository"] == "https://github.com/example/project.git"
    assert first.json()["source_branch"] == "feature/review"
    assert len(listed.json()) == 1
    assert invalid.status_code == 422
