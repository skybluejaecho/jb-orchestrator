from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import (
    CreateUserRequest,
    ExternalExecutionService,
    OrchestrationService,
    RegisterProject,
    ScmPublicationService,
)
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.scm import ScmPublicationStatus
from jb_orchestrator.worker import TaskClaim


async def test_scm_publication_round_trips_and_claims_by_provider_and_scope() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    orchestration = OrchestrationService(uow)
    project = await orchestration.register_project(
        RegisterProject(
            key="example-project",
            name="Example",
            repository_url="https://github.com/example/project.git",
            default_branch="develop",
        )
    )
    created = await orchestration.create_request(
        CreateUserRequest(project_id=project.id, prompt="Implement the feature")
    )
    claim = TaskClaim(
        execution_id=uuid4(),
        run_id=created.run.id,
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
        instructions=None,
        configuration={},
        skills=(),
    )
    executions = ExternalExecutionService(uow)
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
    await executions.finish(claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED)
    publications = ScmPublicationService(uow)

    requested, replayed = await publications.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="Please review.",
        idempotency_key="publish-1",
        requested_by="test",
    )
    repeated, repeated_replayed = await publications.request(
        execution.id,
        provider_key="github",
        target_branch="develop",
        title="Review feature",
        body="Please review.",
        idempotency_key="publish-1",
        requested_by="test",
    )
    claimed = await publications.claim_next(
        worker_id="publisher-a",
        provider_key="github",
        workspace_scope="git-worktree:scope-a",
    )

    assert not replayed
    assert repeated_replayed
    assert repeated.id == requested.id
    assert claimed is not None
    assert claimed.status is ScmPublicationStatus.CLAIMED
    assert claimed.lease_token is not None
    completed = await publications.succeed(
        claimed.id,
        claimed.lease_token,
        {"review_url": "https://github.com/example/project/pull/1", "review_id": "1"},
    )
    assert completed.status is ScmPublicationStatus.SUCCEEDED
    assert (await publications.list_for_execution(execution.id))[0].result == {
        "review_url": "https://github.com/example/project/pull/1",
        "review_id": "1",
    }
    await engine.dispose()
