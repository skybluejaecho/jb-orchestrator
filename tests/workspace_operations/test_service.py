from uuid import uuid4

import pytest

from jb_orchestrator.application import ExternalExecutionService, WorkspaceOperationService
from jb_orchestrator.application.exceptions import ResourceConflict
from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.worker import TaskClaim
from jb_orchestrator.workspace_operations import (
    WorkspaceOperationKind,
    WorkspaceOperationStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def task_claim() -> TaskClaim:
    return TaskClaim(
        execution_id=uuid4(),
        run_id=uuid4(),
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


async def managed_execution(store: MemoryStore, *, terminal: bool = True):
    executions = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    execution = await executions.prepare(
        claim,
        session_key="agent:implementation:1",
        agent_id="implementation",
        workspace_path="C:/worktrees/task",
        workspace_repository_path="C:/projects/example",
        workspace_branch="jb/task/implementation-v1",
        workspace_base_ref="abc123",
        workspace_scope="git-worktree:scope-a",
    )
    if terminal:
        execution = await executions.finish(
            claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED
        )
    return execution


async def test_request_is_idempotent_and_claim_is_scope_routed() -> None:
    store = MemoryStore()
    execution = await managed_execution(store)
    service = WorkspaceOperationService(lambda: MemoryUnitOfWork(store))

    first, replayed = await service.request(
        execution.id,
        kind=WorkspaceOperationKind.INSPECT,
        target_ref="develop",
        idempotency_key="inspect-1",
        requested_by="jarvis",
    )
    repeated, repeated_replayed = await service.request(
        execution.id,
        kind=WorkspaceOperationKind.INSPECT,
        target_ref="develop",
        idempotency_key="inspect-1",
        requested_by="jarvis",
    )

    assert not replayed
    assert repeated_replayed
    assert repeated.id == first.id
    assert (
        await service.claim_next(worker_id="wrong", workspace_scope="git-worktree:scope-b") is None
    )
    claimed = await service.claim_next(
        worker_id="workspace-a", workspace_scope="git-worktree:scope-a"
    )
    assert claimed is not None
    assert claimed.status is WorkspaceOperationStatus.CLAIMED
    assert claimed.lease_token is not None

    completed = await service.succeed(
        claimed.id, claimed.lease_token, {"clean": True, "merged": False}
    )

    assert completed.status is WorkspaceOperationStatus.SUCCEEDED
    assert completed.result == {"clean": True, "merged": False}
    assert [event.event_type for event in store.events[-3:]] == [
        "workspace_operation.requested",
        "workspace_operation.claimed",
        "workspace_operation.succeeded",
    ]


async def test_cleanup_requires_terminal_execution_and_exact_confirmation() -> None:
    store = MemoryStore()
    execution = await managed_execution(store, terminal=False)
    service = WorkspaceOperationService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(DomainValidationError, match="confirmation"):
        await service.request(
            execution.id,
            kind=WorkspaceOperationKind.CLEANUP,
            target_ref="develop",
            idempotency_key="cleanup-1",
            requested_by="jarvis",
            confirmation="wrong",
        )
    with pytest.raises(ResourceConflict, match="terminal"):
        await service.request(
            execution.id,
            kind=WorkspaceOperationKind.CLEANUP,
            target_ref="develop",
            idempotency_key="cleanup-2",
            requested_by="jarvis",
            confirmation=str(execution.id),
        )
