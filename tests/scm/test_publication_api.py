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


async def test_failed_publication_can_be_retried_through_api() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    publications = ScmPublicationService(lambda: MemoryUnitOfWork(store))
    publication, _ = await publications.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="",
        idempotency_key="publish-retry",
        requested_by="jarvis",
    )
    claimed = await publications.claim_next(
        worker_id="publisher-a",
        provider_key="github",
        workspace_scope="git-worktree:scope-a",
    )
    assert claimed is not None and claimed.lease_token is not None
    await publications.fail(claimed.id, claimed.lease_token, "temporary failure")
    app = create_app(scm_publication_service=publications)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        retried = await client.post(f"/v1/scm-publications/{publication.id}/retry")
        repeated = await client.post(f"/v1/scm-publications/{publication.id}/retry")

    assert retried.status_code == 202
    assert retried.json()["status"] == "pending"
    assert retried.json()["attempt_count"] == 1
    assert repeated.status_code == 200
