from uuid import uuid4

from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.worker import TaskClaim
from tests.support import MemoryStore, MemoryUnitOfWork


def task_claim() -> TaskClaim:
    return TaskClaim(
        execution_id=uuid4(),
        run_id=uuid4(),
        node_key="review",
        executor_key="openclaw",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key="execution:review:1",
        visit_count=1,
        attempt_count=1,
        timeout_seconds=300,
        workflow_key="delivery",
        workflow_version=1,
        instructions="Review the implementation.",
        configuration={},
        skills=(),
    )


async def test_prepare_is_idempotent_and_keeps_the_original_session() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()

    first = await service.prepare(
        claim, session_key="agent:reviewer:execution", agent_id="reviewer"
    )
    second = await service.prepare(
        claim, session_key="agent:different:session", agent_id="different"
    )

    assert second.id == first.id
    assert second.external_session_key == "agent:reviewer:execution"
    assert len(store.external_executions) == 1


async def test_external_execution_lifecycle_is_persisted() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:reviewer:execution", agent_id="reviewer")

    accepted = await service.accept(claim.idempotency_key, "openclaw-run-1")
    completed = await service.finish(
        claim.idempotency_key,
        ExternalExecutionStatus.SUCCEEDED,
        terminal_result={"status": "ok", "output": "approved"},
    )

    assert accepted.external_run_id == "openclaw-run-1"
    assert completed.status is ExternalExecutionStatus.SUCCEEDED
    assert completed.terminal_result == {"status": "ok", "output": "approved"}
    assert completed.completed_at is not None
