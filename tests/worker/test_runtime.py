from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from jb_orchestrator.application import BudgetService, TaskDispatchService
from jb_orchestrator.budgets import BudgetReservationStatus, UsageKind
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    ModelProfile,
    ModelRoutingRequest,
    ModelSelection,
    ModelTier,
    NodeModelSelection,
)
from jb_orchestrator.skills import SkillDefinition, SkillSourceKind
from jb_orchestrator.skills.materialization import (
    LocalSkillFetcher,
    SkillMaterializer,
    compute_directory_digest,
)
from jb_orchestrator.worker.models import TaskClaim, TaskResult, TokenUsage
from jb_orchestrator.worker.registry import ExecutorRegistry
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


def running_execution(
    *,
    max_attempts: int = 2,
    executor_key: str = "fake",
    skills: tuple[SkillDefinition, ...] = (),
    run_id: UUID | None = None,
    model_selection: ModelSelection | None = None,
) -> WorkflowExecution:
    definition = WorkflowDefinition(
        key="worker-flow",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(
                key="work",
                kind=NodeKind.TASK,
                max_attempts=max_attempts,
                timeout_seconds=10,
                executor_key=executor_key,
                instructions="Produce the requested artifact.",
                configuration={"model": "test-model"},
                skills=tuple(skill.reference for skill in skills),
                model_routing=(ModelRoutingRequest() if model_selection is not None else None),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(
            definition,
            run_id=run_id or uuid4(),
            skills=skills,
            model_selections=(
                (NodeModelSelection(node_key="work", selection=model_selection),)
                if model_selection is not None
                else ()
            ),
        )
    )
    WorkflowEngine().start(execution)
    return execution


def routed_model_selection() -> ModelSelection:
    profile = ModelProfile(
        key="codex-balanced",
        version=1,
        name="Codex Balanced",
        provider="openai",
        model_id="gpt-codex",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        input_cost_per_million=Decimal("1"),
        output_cost_per_million=Decimal("4"),
        executor_keys=("fake",),
    )
    return DeterministicModelRouter().route(
        ModelRoutingRequest(estimated_input_tokens=100_000, max_output_tokens=10_000),
        (profile,),
        executor_key="fake",
    )


async def test_worker_executes_claim_and_persists_result() -> None:
    store = MemoryStore()
    execution = running_execution()
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))
    executor = FakeExecutor(
        [TaskResult(outcome=NodeOutcome.SUCCESS, output={"artifact": "result.md"})]
    )
    runtime = WorkerRuntime("worker-a", dispatch, ExecutorRegistry({"fake": executor}))

    assert await runtime.run_once() is True
    assert execution.status is WorkflowStatus.SUCCEEDED
    assert execution.nodes["work"].output == {"artifact": "result.md"}
    assert executor.claims[0].lease_token is not None
    assert executor.claims[0].idempotency_key == f"{execution.id}:work:1"
    assert executor.claims[0].instructions == "Produce the requested artifact."
    assert executor.claims[0].configuration == {"model": "test-model"}
    assert [event.event_type for event in store.events] == ["task.claimed", "task.completed"]


async def test_worker_materializes_verified_skills_before_executor(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "skills"
    skill_root = source_root / "review"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    skill = SkillDefinition(
        key="review",
        version=1,
        name="Review",
        description="Review changes",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="review",
        content_digest=compute_directory_digest(skill_root),
    )
    store = MemoryStore()
    execution = running_execution(skills=(skill,))
    store.workflow_executions[execution.id] = execution
    executor = FakeExecutor([TaskResult(outcome=NodeOutcome.SUCCESS)])
    runtime = WorkerRuntime(
        "worker-a",
        TaskDispatchService(lambda: MemoryUnitOfWork(store)),
        ExecutorRegistry({"fake": executor}),
        skill_materializer=SkillMaterializer(
            tmp_path / "cache",
            {SkillSourceKind.LOCAL: LocalSkillFetcher(source_root)},
        ),
    )

    assert await runtime.run_once() is True

    entrypoint = Path(executor.claims[0].skill_paths["review@1"])
    assert entrypoint.read_text(encoding="utf-8") == "# Review\n"
    assert entrypoint.parent.parent == tmp_path / "cache"


async def test_worker_retries_when_skill_verification_fails(tmp_path: Path) -> None:
    source_root = tmp_path / "skills"
    skill_root = source_root / "review"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    skill = SkillDefinition(
        key="review",
        version=1,
        name="Review",
        description="Review changes",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="review",
        content_digest="sha256:" + "0" * 64,
    )
    store = MemoryStore()
    execution = running_execution(skills=(skill,))
    store.workflow_executions[execution.id] = execution
    executor = FakeExecutor([TaskResult(outcome=NodeOutcome.SUCCESS)])
    runtime = WorkerRuntime(
        "worker-a",
        TaskDispatchService(lambda: MemoryUnitOfWork(store)),
        ExecutorRegistry({"fake": executor}),
        skill_materializer=SkillMaterializer(
            tmp_path / "cache",
            {SkillSourceKind.LOCAL: LocalSkillFetcher(source_root)},
        ),
    )

    assert await runtime.run_once() is True

    assert execution.nodes["work"].status is NodeExecutionStatus.READY
    assert not executor.claims
    assert store.events[-1].event_type == "task.failed"


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


async def test_worker_does_not_claim_an_unsupported_executor() -> None:
    store = MemoryStore()
    execution = running_execution(executor_key="codex")
    store.workflow_executions[execution.id] = execution
    dispatch = TaskDispatchService(lambda: MemoryUnitOfWork(store))
    runtime = WorkerRuntime("worker-a", dispatch, ExecutorRegistry())

    assert await runtime.run_once() is False
    assert execution.nodes["work"].status is NodeExecutionStatus.READY


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
    runtime = WorkerRuntime("worker-a", dispatch, ExecutorRegistry({"fake": executor}))

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


async def test_worker_reserves_and_settles_actual_model_usage() -> None:
    store = MemoryStore()
    project = Project(
        key="budget-worker",
        name="Budget Worker",
        repository_url="https://example.com/repository.git",
    )
    request = UserRequest(project_id=project.id, prompt="Implement")
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run
    execution = running_execution(run_id=run.id, model_selection=routed_model_selection())
    store.workflow_executions[execution.id] = execution
    budget = BudgetService(lambda: MemoryUnitOfWork(store))
    await budget.configure(project.id, Decimal("1.00"))
    executor = FakeExecutor(
        [
            TaskResult(
                outcome=NodeOutcome.SUCCESS,
                usage=TokenUsage(input_tokens=50_000, output_tokens=5_000),
            )
        ]
    )
    runtime = WorkerRuntime(
        "worker-a",
        TaskDispatchService(lambda: MemoryUnitOfWork(store)),
        ExecutorRegistry({"fake": executor}),
        budget_service=budget,
    )

    assert await runtime.run_once() is True

    account = store.budget_accounts[project.id]
    reservation = next(iter(store.budget_reservations.values()))
    assert execution.status is WorkflowStatus.SUCCEEDED
    assert account.reserved_usd == Decimal("0.000000")
    assert account.spent_usd == Decimal("0.070000")
    assert reservation.status is BudgetReservationStatus.SETTLED
    assert store.usage_records[0].kind is UsageKind.ACTUAL


async def test_worker_forfeits_reservation_after_final_missing_usage() -> None:
    store = MemoryStore()
    project = Project(
        key="budget-forfeit",
        name="Budget Forfeit",
        repository_url="https://example.com/repository.git",
    )
    request = UserRequest(project_id=project.id, prompt="Implement")
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run
    execution = running_execution(
        max_attempts=1,
        run_id=run.id,
        model_selection=routed_model_selection(),
    )
    store.workflow_executions[execution.id] = execution
    budget = BudgetService(lambda: MemoryUnitOfWork(store))
    await budget.configure(project.id, Decimal("1.00"))
    executor = FakeExecutor([TaskResult(outcome=NodeOutcome.SUCCESS)])
    runtime = WorkerRuntime(
        "worker-a",
        TaskDispatchService(lambda: MemoryUnitOfWork(store)),
        ExecutorRegistry({"fake": executor}),
        budget_service=budget,
    )

    assert await runtime.run_once() is True

    reservation = next(iter(store.budget_reservations.values()))
    assert execution.status is WorkflowStatus.FAILED
    assert reservation.status is BudgetReservationStatus.FORFEITED
    assert store.budget_accounts[project.id].spent_usd == Decimal("0.140000")
    assert store.usage_records[0].kind is UsageKind.ESTIMATED_FORFEIT
