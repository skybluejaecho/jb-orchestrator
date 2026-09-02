from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowExecution,
    WorkflowExecutionError,
    WorkflowSnapshot,
    WorkflowStatus,
)


def build_delivery_execution(*, max_visits: int = 2) -> WorkflowExecution:
    definition = WorkflowDefinition(
        key="delivery",
        version=1,
        entry_node="plan",
        nodes=(
            NodeDefinition(key="plan", kind=NodeKind.TASK),
            NodeDefinition(key="approval", kind=NodeKind.APPROVAL),
            NodeDefinition(key="implement", kind=NodeKind.TASK, max_visits=max_visits),
            NodeDefinition(key="verify", kind=NodeKind.TASK, max_visits=max_visits),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
            NodeDefinition(
                key="rejected", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.FAILED
            ),
        ),
        edges=(
            EdgeDefinition(source="plan", outcome=NodeOutcome.SUCCESS, target="approval"),
            EdgeDefinition(source="approval", outcome=NodeOutcome.APPROVED, target="implement"),
            EdgeDefinition(source="approval", outcome=NodeOutcome.REJECTED, target="rejected"),
            EdgeDefinition(source="implement", outcome=NodeOutcome.SUCCESS, target="verify"),
            EdgeDefinition(source="verify", outcome=NodeOutcome.SUCCESS, target="done"),
            EdgeDefinition(source="verify", outcome=NodeOutcome.FAILURE, target="implement"),
        ),
    )
    snapshot = WorkflowSnapshot.from_definition(definition, run_id=uuid4())
    return WorkflowExecution.create(snapshot)


def execute_until_approval(engine: WorkflowEngine, execution: WorkflowExecution) -> None:
    engine.start(execution)
    engine.begin_task(execution, "plan")
    engine.complete_task(execution, "plan", NodeOutcome.SUCCESS, output={"plan": "ready"})


def test_happy_path_pauses_for_approval_and_succeeds() -> None:
    engine = WorkflowEngine()
    execution = build_delivery_execution()

    execute_until_approval(engine, execution)
    assert execution.status is WorkflowStatus.AWAITING_APPROVAL
    assert execution.nodes["approval"].status is NodeExecutionStatus.AWAITING_APPROVAL

    engine.resolve_approval(execution, "approval", approved=True)
    engine.begin_task(execution, "implement")
    engine.complete_task(execution, "implement", NodeOutcome.SUCCESS)
    engine.begin_task(execution, "verify")
    engine.complete_task(execution, "verify", NodeOutcome.SUCCESS)

    assert execution.status is WorkflowStatus.SUCCEEDED
    assert execution.is_terminal
    assert execution.nodes["done"].status is NodeExecutionStatus.SUCCEEDED


def test_rejected_approval_routes_to_failure_terminal() -> None:
    engine = WorkflowEngine()
    execution = build_delivery_execution()
    execute_until_approval(engine, execution)

    engine.resolve_approval(execution, "approval", approved=False)

    assert execution.status is WorkflowStatus.FAILED
    assert execution.failure_reason == "workflow reached failure terminal: rejected"


def test_repair_loop_fails_when_node_visit_limit_is_exceeded() -> None:
    engine = WorkflowEngine()
    execution = build_delivery_execution(max_visits=2)
    execute_until_approval(engine, execution)
    engine.resolve_approval(execution, "approval", approved=True)

    for _ in range(2):
        engine.begin_task(execution, "implement")
        engine.complete_task(execution, "implement", NodeOutcome.SUCCESS)
        engine.begin_task(execution, "verify")
        engine.complete_task(execution, "verify", NodeOutcome.FAILURE)

    assert execution.status is WorkflowStatus.FAILED
    assert execution.failure_reason == "node visit limit exceeded: implement"
    assert execution.nodes["implement"].visit_count == 2


def test_technical_failure_retries_then_fails_workflow() -> None:
    definition = WorkflowDefinition(
        key="retry",
        version=1,
        entry_node="task",
        nodes=(
            NodeDefinition(key="task", kind=NodeKind.TASK, max_attempts=2),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(definition, run_id=uuid4())
    )
    engine = WorkflowEngine()
    engine.start(execution)

    engine.begin_task(execution, "task")
    engine.fail_task(execution, "task", "temporary")
    assert execution.nodes["task"].status is NodeExecutionStatus.READY

    engine.begin_task(execution, "task")
    engine.fail_task(execution, "task", "permanent")

    assert execution.status is WorkflowStatus.FAILED
    assert execution.failure_reason == "permanent"


def test_missing_outcome_edge_fails_deterministically() -> None:
    definition = WorkflowDefinition(
        key="missing-edge",
        version=1,
        entry_node="task",
        nodes=(
            NodeDefinition(key="task", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(definition, run_id=uuid4())
    )
    engine = WorkflowEngine()
    engine.start(execution)
    engine.begin_task(execution, "task")

    engine.complete_task(execution, "task", NodeOutcome.FAILURE)

    assert execution.status is WorkflowStatus.FAILED
    assert execution.failure_reason == "no edge for task:failure"


def test_cancel_stops_active_node_and_is_not_repeatable() -> None:
    engine = WorkflowEngine()
    execution = build_delivery_execution()
    engine.start(execution)

    engine.cancel(execution)

    assert execution.status is WorkflowStatus.CANCELLED
    assert execution.nodes["plan"].status is NodeExecutionStatus.CANCELLED
    with pytest.raises(WorkflowExecutionError, match="terminal"):
        engine.cancel(execution)


def test_task_lease_requires_matching_unexpired_token() -> None:
    engine = WorkflowEngine()
    execution = build_delivery_execution()
    started_at = datetime(2026, 9, 1, tzinfo=UTC)
    engine.start(execution, at=started_at)
    node = engine.claim_task(
        execution,
        "plan",
        worker_id="worker-1",
        lease_seconds=30,
        at=started_at,
    )
    assert node.lease_token is not None

    with pytest.raises(WorkflowExecutionError, match="does not match"):
        engine.complete_task(
            execution,
            "plan",
            NodeOutcome.SUCCESS,
            lease_token=uuid4(),
            at=started_at + timedelta(seconds=1),
        )
    with pytest.raises(WorkflowExecutionError, match="expired"):
        engine.complete_task(
            execution,
            "plan",
            NodeOutcome.SUCCESS,
            lease_token=node.lease_token,
            at=started_at + timedelta(seconds=30),
        )


def test_expired_lease_consumes_attempt_and_returns_to_ready() -> None:
    definition = WorkflowDefinition(
        key="leased-retry",
        version=1,
        entry_node="task",
        nodes=(
            NodeDefinition(key="task", kind=NodeKind.TASK, max_attempts=2),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    execution = WorkflowExecution.create(
        WorkflowSnapshot.from_definition(definition, run_id=uuid4())
    )
    engine = WorkflowEngine()
    started_at = datetime(2026, 9, 1, tzinfo=UTC)
    engine.start(execution, at=started_at)
    engine.claim_task(execution, "task", worker_id="worker-1", lease_seconds=10, at=started_at)

    engine.expire_task(execution, "task", at=started_at + timedelta(seconds=10))

    node = execution.nodes["task"]
    assert node.status is NodeExecutionStatus.READY
    assert node.attempt_count == 1
    assert node.lease_token is None
