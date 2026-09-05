from uuid import uuid4

import pytest

from jb_orchestrator.application import ExternalExecutionService, ScmPublicationService
from jb_orchestrator.application.exceptions import ResourceConflict
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.scm import ScmPublicationFailureCode, ScmPublicationStatus
from jb_orchestrator.worker import TaskClaim
from tests.support import MemoryStore, MemoryUnitOfWork


async def managed_execution(store: MemoryStore, *, terminal: bool = True, released: bool = False):
    project = Project(
        key="example-project",
        name="Example",
        repository_url="https://github.com/example/project.git",
        default_branch="develop",
    )
    request = UserRequest(project_id=project.id, prompt="Implement the change")
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run
    claim = TaskClaim(
        execution_id=uuid4(),
        run_id=run.id,
        node_key="implementation",
        executor_key="openclaw",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key="execution:implementation:1",
        visit_count=1,
        attempt_count=1,
        timeout_seconds=300,
        workflow_key="delivery",
        workflow_version=1,
        instructions="Implement the change.",
        configuration={},
        skills=(),
    )
    executions = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    execution = await executions.prepare(
        claim,
        session_key="agent:implementation:1",
        agent_id="implementation",
        workspace_path="C:/worktrees/task",
        workspace_repository_path="C:/projects/example",
        workspace_branch="feature/review",
        workspace_base_ref="abc123",
        workspace_scope="git-worktree:scope-a",
    )
    if terminal:
        execution = await executions.finish(
            claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED
        )
    if released:
        execution.release_workspace()
        store.external_executions[execution.idempotency_key] = execution
    return execution


async def test_request_derives_repository_and_source_branch_then_routes_claim() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    service = ScmPublicationService(lambda: MemoryUnitOfWork(store))

    first, replayed = await service.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="Please review.",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )
    repeated, repeated_replayed = await service.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="Please review.",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )

    assert not replayed
    assert repeated_replayed
    assert repeated.id == first.id
    assert first.repository == "https://github.com/example/project.git"
    assert first.source_branch == "feature/review"
    assert (
        await service.claim_next(
            worker_id="wrong-provider",
            provider_key="gitlab",
            workspace_scope="git-worktree:scope-a",
        )
        is None
    )
    claimed = await service.claim_next(
        worker_id="publisher-a",
        provider_key="github",
        workspace_scope="git-worktree:scope-a",
    )
    assert claimed is not None
    assert claimed.status is ScmPublicationStatus.CLAIMED
    assert claimed.lease_token is not None

    completed = await service.succeed(
        claimed.id,
        claimed.lease_token,
        {"review_url": "https://github.com/example/project/pull/1", "review_id": "1"},
    )

    assert completed.status is ScmPublicationStatus.SUCCEEDED
    assert [event.event_type for event in store.events[-3:]] == [
        "scm_publication.requested",
        "scm_publication.claimed",
        "scm_publication.succeeded",
    ]


async def test_request_requires_terminal_unreleased_managed_workspace() -> None:
    store = MemoryStore()
    active = await managed_execution(store, terminal=False)
    service = ScmPublicationService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(ResourceConflict, match="terminal"):
        await service.request(
            active.id,
            provider_key="github",
            target_branch="develop",
            title="Review feature",
            body="",
            idempotency_key="publish-active",
            requested_by="jarvis",
        )

    released = await managed_execution(store, released=True)
    with pytest.raises(ResourceConflict, match="unreleased"):
        await service.request(
            released.id,
            provider_key="github",
            target_branch="develop",
            title="Review feature",
            body="",
            idempotency_key="publish-released",
            requested_by="jarvis",
        )


async def test_reused_idempotency_key_must_match_original_payload() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    service = ScmPublicationService(lambda: MemoryUnitOfWork(store))
    await service.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )

    with pytest.raises(ResourceConflict, match="another publication"):
        await service.request(
            execution.id,
            provider_key="github",
            target_branch="main",
            title="Review feature",
            body="",
            idempotency_key="publish-1",
            requested_by="jarvis",
        )


async def test_failed_publication_retry_preserves_record_and_attempt_history() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    service = ScmPublicationService(lambda: MemoryUnitOfWork(store))
    requested, _ = await service.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="",
        idempotency_key="publish-retry",
        requested_by="jarvis",
    )
    claimed = await service.claim_next(
        worker_id="publisher-a",
        provider_key="github",
        workspace_scope="git-worktree:scope-a",
    )
    assert claimed is not None and claimed.lease_token is not None
    failed = await service.fail(
        claimed.id,
        claimed.lease_token,
        "temporary failure",
        code=ScmPublicationFailureCode.PROVIDER_UNAVAILABLE,
        retryable=True,
    )

    assert failed.failure_code is ScmPublicationFailureCode.PROVIDER_UNAVAILABLE
    assert failed.failure_retryable is True
    assert store.events[-1].payload["failure_code"] == "provider_unavailable"
    assert store.events[-1].payload["failure_retryable"] is True

    retried, replayed = await service.retry(failed.id, requested_by="jarvis")
    repeated, repeated_replayed = await service.retry(failed.id, requested_by="jarvis")

    assert retried.id == requested.id
    assert retried.status is ScmPublicationStatus.PENDING
    assert retried.attempt_count == 1
    assert not replayed
    assert repeated_replayed
    assert repeated.id == requested.id
    assert store.events[-1].event_type == "scm_publication.retried"
    assert store.events[-1].payload["actor"] == "jarvis"
