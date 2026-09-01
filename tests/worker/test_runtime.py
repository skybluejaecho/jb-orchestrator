from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jb_orchestrator.application import TaskDispatchService
from jb_orchestrator.worker.models import TaskClaim, TaskResult
from jb_orchestrator.worker.runtime import WorkerRuntime
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowExecution,
    WorkflowSnapshot,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


class FakeExecutor:
    def __init__(self, results: Sequence[TaskResult | Exception]) -> None:
        self._results = iter(results)
        self.claims: list[TaskClaim] = []

    async def execute(self, claim: TaskClaim) -> TaskResult:
        self.claims.append(claim)
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result


def running_execution(*, max_attempts: int = 2) -> WorkflowExecution:
    definition = WorkflowDefinition(
        key="worker-flow",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(
                key="work", kind=NodeKind.TASK, max_attempts=max_attempts, timeout_seconds=10
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(definition, run_id=uuid4())
    )
    WorkflowEngine().start(execution)
    return execution


async def test_worker_executes_claim_and_persists_result() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))
    executor = FakeExecutor(
        [TaskResult(outcome=NodeOutcome.SUCCESS, output={"artifact": "result.md"})]
    )
    runtime = WorkerRuntime("worker-a", dispatch, executor)

    assert await runtime.run_once() is True
    assert execution.status is WorkflowStatus.SUCCEEDED
    assert execution.nodes["work"].output == {"artifact": "result.md"}
    assert executor.claims[0].lease_token is not None
    assert executor.claims[0].idempotency_key == f"{execution.id}:work:1"
    assert [event.event_type for event in store.events] == ["task.claimed", "task.completed"]


async def test_competing_workers_cannot_claim_running_node() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))

    first = await dispatch.claim_next("worker-a")
    second = await dispatch.claim_next("worker-b")

    assert first is not None
    assert second is None
    assert execution.nodes["work"].worker_id == "worker-a"


async def test_executor_failure_retries_on_next_poll() -> None:
    store = MemoryStore()
    execution = running_execution(max_attempts=2)
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))
    executor = FakeExecutor(
        [
            RuntimeError("temporary"),
            TaskResult(outcome=NodeOutcome.SUCCESS),
        ]
    )
    runtime = WorkerRuntime("worker-a", dispatch, executor)

    await runtime.run_once()
    assert execution.nodes["work"].status is NodeExecutionStatus.READY
    await runtime.run_once()

    assert execution.status is WorkflowStatus.SUCCEEDED
    assert [claim.attempt_count for claim in executor.claims] == [1, 2]
    assert len({claim.idempotency_key for claim in executor.claims}) == 1


async def test_expired_claim_is_recovered_before_new_work() -> None:
    store = MemoryStore()
    execution = running_execution(max_attempts=2)
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store), lease_grace_seconds=5)
    claimed_at = datetime(2026, 9, 1, tzinfo=UTC)
    claim = await dispatch.claim_next("dead-worker", at=claimed_at)
    assert claim is not None

    recovered = await dispatch.recover_expired(at=claimed_at + timedelta(seconds=15))

    assert recovered is True
    assert execution.nodes["work"].status is NodeExecutionStatus.READY
    assert execution.nodes["work"].lease_token is None
    assert store.events[-1].event_type == "task.lease_expired"


async def test_heartbeat_extends_an_active_lease() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store), lease_grace_seconds=5)
    claimed_at = datetime(2026, 9, 1, tzinfo=UTC)
    claim = await dispatch.claim_next("worker-a", at=claimed_at)
    assert claim is not None

    await dispatch.heartbeat(claim, at=claimed_at + timedelta(seconds=5))

    assert execution.nodes["work"].lease_expires_at == claimed_at + timedelta(seconds=20)
    assert store.events[-1].event_type == "task.lease_renewed"
