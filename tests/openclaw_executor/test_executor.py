from typing import Any
from uuid import uuid4

from jb_openclaw_executor import OpenClawExecutor

from jb_orchestrator.application import ExternalExecutionService
from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.phase_packs import (
    PhaseInputDefinition,
    PhasePackDefinition,
)
from jb_orchestrator.worker import TaskArtifactInput, TaskClaim, TaskContextEnvelope
from jb_orchestrator.workflows import NodeOutcome, WorkflowRequestContext
from tests.support import MemoryStore, MemoryUnitOfWork


class FakeBridge:
    def __init__(self) -> None:
        self.starts: list[dict[str, Any]] = []
        self.waits: list[tuple[str, int]] = []
        self.cancels: list[str] = []
        self.terminal: dict[str, Any] = {
            "status": "ok",
            "output": "approved",
            "usage": {"inputTokens": 120, "outputTokens": 30},
        }

    async def start(self, request: dict[str, Any]) -> dict[str, Any]:
        self.starts.append(request)
        return {"runId": "openclaw-run-1", "acceptedAt": 1234}

    async def wait(self, run_id: str, timeout_ms: int) -> dict[str, Any]:
        self.waits.append((run_id, timeout_ms))
        return self.terminal

    async def cancel(self, run_id: str) -> dict[str, Any]:
        self.cancels.append(run_id)
        return {"ok": True}


def task_claim() -> TaskClaim:
    execution_id = uuid4()
    plan_artifact = TaskArtifact(
        execution_id=execution_id,
        producer_node_key="plan",
        visit_count=1,
        outcome=NodeOutcome.SUCCESS,
        content={"requirements": ["keep context durable"]},
    )
    return TaskClaim(
        execution_id=execution_id,
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
        configuration={"agent_id": "reviewer", "thinking": "low"},
        skills=(),
        phase_pack=PhasePackDefinition(
            key="review",
            version=1,
            name="Review",
            description="Review the implementation evidence.",
            instructions="Check correctness and identify risks.",
            inputs=(PhaseInputDefinition(key="implementation", description="Work result"),),
            output_contract={"required": ["verdict", "findings"]},
        ),
        context=TaskContextEnvelope(
            request=WorkflowRequestContext(
                request_id=uuid4(),
                project_id=uuid4(),
                project_key="delivery-project",
                project_name="Delivery Project",
                repository_url="https://example.com/delivery.git",
                default_branch="develop",
                prompt="Implement the approved change.",
                title="Delivery request",
            ),
            upstream_artifacts=(plan_artifact,),
            named_inputs=(TaskArtifactInput(name="implementation", artifact=plan_artifact),),
        ),
        skill_paths={"review@1": "C:/skills/review/SKILL.md"},
    )


async def test_executor_persists_run_and_normalizes_terminal_result() -> None:
    store = MemoryStore()
    bridge = FakeBridge()
    executor = OpenClawExecutor(ExternalExecutionService(lambda: MemoryUnitOfWork(store)), bridge)
    claim = task_claim()

    result = await executor.execute(claim)

    mapping = store.external_executions[claim.idempotency_key]
    assert result.outcome is NodeOutcome.SUCCESS
    assert result.usage is not None
    assert result.usage.input_tokens == 120
    assert mapping.status is ExternalExecutionStatus.SUCCEEDED
    assert mapping.external_run_id == "openclaw-run-1"
    assert bridge.starts[0]["sessionKey"].startswith("agent:reviewer:jb:")
    assert bridge.starts[0]["idempotencyKey"] == claim.idempotency_key
    assert "C:/skills/review/SKILL.md" in bridge.starts[0]["message"]
    assert "Implement the approved change." in bridge.starts[0]["message"]
    assert "https://example.com/delivery.git" in bridge.starts[0]["message"]
    assert "keep context durable" in bridge.starts[0]["message"]
    assert "Named phase inputs" in bridge.starts[0]["message"]
    assert "Phase input contract" in bridge.starts[0]["message"]
    assert '"verdict"' in bridge.starts[0]["message"]
    assert bridge.waits == [("openclaw-run-1", 300_000)]
    assert result.output["provider"] == "openclaw"


async def test_executor_promotes_structured_terminal_output_to_phase_artifact() -> None:
    store = MemoryStore()
    bridge = FakeBridge()
    bridge.terminal["output"] = '{"verdict":"approved","findings":[]}'
    executor = OpenClawExecutor(ExternalExecutionService(lambda: MemoryUnitOfWork(store)), bridge)

    result = await executor.execute(task_claim())

    assert result.output == {"verdict": "approved", "findings": []}
    assert "Return the final phase result as one JSON object" in bridge.starts[0]["message"]


async def test_executor_accepts_object_terminal_output() -> None:
    store = MemoryStore()
    bridge = FakeBridge()
    bridge.terminal["output"] = {"verdict": "approved", "findings": []}
    executor = OpenClawExecutor(ExternalExecutionService(lambda: MemoryUnitOfWork(store)), bridge)

    result = await executor.execute(task_claim())

    assert result.output == {"verdict": "approved", "findings": []}


async def test_executor_returns_persisted_terminal_result_without_duplicate_start() -> None:
    store = MemoryStore()
    bridge = FakeBridge()
    executor = OpenClawExecutor(ExternalExecutionService(lambda: MemoryUnitOfWork(store)), bridge)
    claim = task_claim()

    first = await executor.execute(claim)
    second = await executor.execute(claim)

    assert first == second
    assert len(bridge.starts) == 1
    assert len(bridge.waits) == 1


async def test_executor_resumes_waiting_for_an_active_run_after_restart() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    bridge = FakeBridge()
    executor = OpenClawExecutor(service, bridge)
    claim = task_claim()
    await service.prepare(claim, session_key="agent:reviewer:existing", agent_id="reviewer")
    await service.accept(claim.idempotency_key, "existing-run")

    result = await executor.execute(claim)

    assert result.outcome is NodeOutcome.SUCCESS
    assert bridge.starts == []
    assert bridge.waits == [("existing-run", 300_000)]


async def test_cancel_aborts_exact_active_run_and_marks_mapping() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    bridge = FakeBridge()
    executor = OpenClawExecutor(service, bridge)
    claim = task_claim()
    await service.prepare(claim, session_key="agent:reviewer:existing", agent_id="reviewer")
    await service.accept(claim.idempotency_key, "existing-run")

    await executor.cancel(claim)

    assert bridge.cancels == ["existing-run"]
    assert (
        store.external_executions[claim.idempotency_key].status is ExternalExecutionStatus.CANCELLED
    )


async def test_wait_timeout_aborts_run_before_raising() -> None:
    store = MemoryStore()
    bridge = FakeBridge()
    bridge.terminal = {"status": "timeout"}
    executor = OpenClawExecutor(ExternalExecutionService(lambda: MemoryUnitOfWork(store)), bridge)
    claim = task_claim()

    try:
        await executor.execute(claim)
    except TimeoutError as exc:
        assert "run was cancelled" in str(exc)
    else:
        raise AssertionError("executor did not raise TimeoutError")

    assert bridge.cancels == ["openclaw-run-1"]
    assert (
        store.external_executions[claim.idempotency_key].status is ExternalExecutionStatus.CANCELLED
    )
