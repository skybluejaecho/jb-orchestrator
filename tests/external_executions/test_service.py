from uuid import uuid4

import pytest

from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.domain import InvalidStateTransition
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
    assert [event.event_type for event in store.events] == ["external_execution.prepared"]


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
    assert [event.event_type for event in store.events] == [
        "external_execution.prepared",
        "external_execution.accepted",
        "external_execution.finished",
    ]
    assert store.events[-1].payload["status"] == "succeeded"


async def test_repeated_terminal_callback_does_not_duplicate_event() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:reviewer:execution", agent_id="reviewer")
    await service.accept(claim.idempotency_key, "openclaw-run-1")

    first = await service.finish(claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED)
    repeated = await service.finish(claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED)

    assert repeated.id == first.id
    assert [event.event_type for event in store.events].count("external_execution.finished") == 1

    with pytest.raises(InvalidStateTransition):
        await service.finish(claim.idempotency_key, ExternalExecutionStatus.FAILED)


async def test_repeated_accept_callback_does_not_duplicate_event() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim()
    await service.prepare(claim, session_key="agent:reviewer:execution", agent_id="reviewer")

    first = await service.accept(claim.idempotency_key, "openclaw-run-1")
    repeated = await service.accept(claim.idempotency_key, "openclaw-run-1")

    assert repeated.id == first.id
    assert [event.event_type for event in store.events].count("external_execution.accepted") == 1


async def test_external_executions_can_be_filtered_and_loaded_by_id() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    first_claim = task_claim()
    second_claim = task_claim()
    second_claim = TaskClaim(
        execution_id=second_claim.execution_id,
        run_id=second_claim.run_id,
        node_key=second_claim.node_key,
        executor_key=second_claim.executor_key,
        worker_id=second_claim.worker_id,
        lease_token=second_claim.lease_token,
        idempotency_key="execution:review:2",
        visit_count=second_claim.visit_count,
        attempt_count=second_claim.attempt_count,
        timeout_seconds=second_claim.timeout_seconds,
        workflow_key=second_claim.workflow_key,
        workflow_version=second_claim.workflow_version,
        instructions=second_claim.instructions,
        configuration=second_claim.configuration,
        skills=second_claim.skills,
    )
    first = await service.prepare(first_claim, session_key="agent:first", agent_id=None)
    await service.prepare(second_claim, session_key="agent:second", agent_id=None)
    await service.accept(first_claim.idempotency_key, "run-first")

    active = await service.list(status=ExternalExecutionStatus.ACTIVE)
    by_workflow = await service.list(workflow_execution_id=second_claim.execution_id)

    assert [execution.id for execution in active] == [first.id]
    assert [execution.run_id for execution in by_workflow] == [second_claim.run_id]
    assert (await service.get_by_id(first.id)).id == first.id
