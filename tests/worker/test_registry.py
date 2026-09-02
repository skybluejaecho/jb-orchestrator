from dataclasses import dataclass

import pytest

from jb_orchestrator.application import TaskDispatchService
from jb_orchestrator.worker.models import TaskClaim, TaskResult
from jb_orchestrator.worker.registry import (
    ExecutorNotFoundError,
    ExecutorRegistrationError,
    ExecutorRegistry,
)
from jb_orchestrator.workflows import NodeOutcome
from tests.support import MemoryStore, MemoryUnitOfWork
from tests.worker.test_runtime import FakeExecutor, running_execution


@dataclass(frozen=True)
class FakeEntryPoint:
    name: str
    value: object

    def load(self) -> object:
        return self.value


class SyncExecutor:
    def execute(self, claim: TaskClaim) -> TaskResult:
        return TaskResult(outcome=NodeOutcome.SUCCESS)


class SyncCancellationExecutor:
    async def execute(self, claim: TaskClaim) -> TaskResult:
        return TaskResult(outcome=NodeOutcome.SUCCESS)

    def cancel(self, claim: TaskClaim) -> None:
        return None


async def test_registry_routes_claim_to_selected_executor() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))
    claim = await dispatch.claim_next("worker-a", {"fake"})
    assert claim is not None
    executor = FakeExecutor([TaskResult(outcome=NodeOutcome.SUCCESS)])
    registry = ExecutorRegistry({"fake": executor})

    result = await registry.execute(claim)

    assert result.outcome is NodeOutcome.SUCCESS
    assert executor.claims == [claim]


def test_registry_discovers_installed_factory_entry_points() -> None:
    executor = FakeExecutor([TaskResult(outcome=NodeOutcome.SUCCESS)])
    registry = ExecutorRegistry.from_entry_points(
        [FakeEntryPoint(name="fake", value=lambda: executor)]
    )

    assert registry.supported_keys == frozenset({"fake"})


def test_registry_rejects_duplicate_keys() -> None:
    executor = FakeExecutor([])
    registry = ExecutorRegistry({"fake": executor})

    with pytest.raises(ExecutorRegistrationError, match="already registered"):
        registry.register("fake", executor)


def test_registry_rejects_synchronous_executor() -> None:
    with pytest.raises(ExecutorRegistrationError, match="must be async"):
        ExecutorRegistry({"sync": SyncExecutor()})  # type: ignore[dict-item]


def test_registry_rejects_synchronous_optional_cancel_hook() -> None:
    with pytest.raises(ExecutorRegistrationError, match="cancel method must be async"):
        ExecutorRegistry({"sync-cancel": SyncCancellationExecutor()})


async def test_registry_rejects_unregistered_claim() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    claim = await TaskDispatchService(lambda: MemoryUnitOfWork(store)).claim_next("worker-a")
    assert claim is not None
    unknown_claim = TaskClaim(
        execution_id=claim.execution_id,
        run_id=claim.run_id,
        node_key=claim.node_key,
        executor_key="unknown",
        worker_id=claim.worker_id,
        lease_token=claim.lease_token,
        idempotency_key=claim.idempotency_key,
        visit_count=claim.visit_count,
        attempt_count=claim.attempt_count,
        timeout_seconds=claim.timeout_seconds,
        workflow_key=claim.workflow_key,
        workflow_version=claim.workflow_version,
        instructions=claim.instructions,
        configuration=claim.configuration,
        skills=claim.skills,
    )

    with pytest.raises(ExecutorNotFoundError, match="not registered"):
        await ExecutorRegistry().execute(unknown_claim)
