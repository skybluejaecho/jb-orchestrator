"""Deterministic workflow state transition engine."""

from datetime import UTC, datetime
from typing import Any

from jb_orchestrator.workflows.exceptions import WorkflowExecutionError
from jb_orchestrator.workflows.models import (
    NodeExecution,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowExecution,
    WorkflowStatus,
)


class WorkflowEngine:
    """Mutate a workflow aggregate without performing external I/O."""

    def start(self, execution: WorkflowExecution, *, at: datetime | None = None) -> None:
        if execution.status is not WorkflowStatus.PENDING:
            raise WorkflowExecutionError("only a pending workflow can be started")
        changed_at = at or datetime.now(UTC)
        execution.status = WorkflowStatus.RUNNING
        execution.started_at = changed_at
        self._touch(execution, changed_at)
        self._activate(execution, execution.snapshot.entry_node, changed_at)

    def begin_task(
        self, execution: WorkflowExecution, node_key: str, *, at: datetime | None = None
    ) -> NodeExecution:
        node = self._node_execution(execution, node_key)
        definition = execution.snapshot.node(node_key)
        if definition.kind is not NodeKind.TASK or node.status is not NodeExecutionStatus.READY:
            raise WorkflowExecutionError("only a ready task node can begin")
        if node.attempt_count >= definition.max_attempts:
            raise WorkflowExecutionError("node attempt limit has been reached")
        changed_at = at or datetime.now(UTC)
        node.status = NodeExecutionStatus.RUNNING
        node.attempt_count += 1
        node.started_at = changed_at
        node.updated_at = changed_at
        self._touch(execution, changed_at)
        return node

    def complete_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        outcome: NodeOutcome,
        *,
        output: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        if node.status is not NodeExecutionStatus.RUNNING:
            raise WorkflowExecutionError("only a running task node can complete")
        if outcome not in {NodeOutcome.SUCCESS, NodeOutcome.FAILURE}:
            raise WorkflowExecutionError("task nodes require success or failure outcome")
        changed_at = at or datetime.now(UTC)
        node.status = NodeExecutionStatus.SUCCEEDED
        node.outcome = outcome
        node.output = output
        node.completed_at = changed_at
        node.updated_at = changed_at
        self._touch(execution, changed_at)
        self._route(execution, node_key, outcome, changed_at)

    def fail_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        reason: str,
        *,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        definition = execution.snapshot.node(node_key)
        if node.status is not NodeExecutionStatus.RUNNING:
            raise WorkflowExecutionError("only a running task node can fail")
        changed_at = at or datetime.now(UTC)
        if node.attempt_count < definition.max_attempts:
            node.status = NodeExecutionStatus.READY
            node.updated_at = changed_at
            self._touch(execution, changed_at)
            return
        node.status = NodeExecutionStatus.FAILED
        node.completed_at = changed_at
        node.updated_at = changed_at
        self._fail(execution, reason.strip() or "task execution failed", changed_at)

    def resolve_approval(
        self,
        execution: WorkflowExecution,
        node_key: str,
        *,
        approved: bool,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        if node.status is not NodeExecutionStatus.AWAITING_APPROVAL:
            raise WorkflowExecutionError("node is not awaiting approval")
        changed_at = at or datetime.now(UTC)
        outcome = NodeOutcome.APPROVED if approved else NodeOutcome.REJECTED
        node.status = NodeExecutionStatus.SUCCEEDED
        node.outcome = outcome
        node.completed_at = changed_at
        node.updated_at = changed_at
        execution.status = WorkflowStatus.RUNNING
        self._touch(execution, changed_at)
        self._route(execution, node_key, outcome, changed_at)

    def cancel(self, execution: WorkflowExecution, *, at: datetime | None = None) -> None:
        if execution.is_terminal:
            raise WorkflowExecutionError("terminal workflow cannot be cancelled")
        changed_at = at or datetime.now(UTC)
        for node in execution.nodes.values():
            if node.status in {
                NodeExecutionStatus.READY,
                NodeExecutionStatus.RUNNING,
                NodeExecutionStatus.AWAITING_APPROVAL,
            }:
                node.status = NodeExecutionStatus.CANCELLED
                node.completed_at = changed_at
                node.updated_at = changed_at
        execution.status = WorkflowStatus.CANCELLED
        execution.completed_at = changed_at
        self._touch(execution, changed_at)

    def _route(
        self,
        execution: WorkflowExecution,
        source: str,
        outcome: NodeOutcome,
        changed_at: datetime,
    ) -> None:
        target = execution.snapshot.target(source, outcome)
        if target is None:
            self._fail(execution, f"no edge for {source}:{outcome}", changed_at)
            return
        self._activate(execution, target, changed_at)

    def _activate(self, execution: WorkflowExecution, node_key: str, changed_at: datetime) -> None:
        node = self._node_execution(execution, node_key)
        definition = execution.snapshot.node(node_key)
        if node.visit_count >= definition.max_visits:
            self._fail(execution, f"node visit limit exceeded: {node_key}", changed_at)
            return

        node.visit_count += 1
        node.attempt_count = 0
        node.outcome = None
        node.output = None
        node.started_at = None
        node.completed_at = None
        node.updated_at = changed_at

        if definition.kind is NodeKind.TASK:
            node.status = NodeExecutionStatus.READY
        elif definition.kind is NodeKind.APPROVAL:
            node.status = NodeExecutionStatus.AWAITING_APPROVAL
            execution.status = WorkflowStatus.AWAITING_APPROVAL
        else:
            node.status = NodeExecutionStatus.SUCCEEDED
            node.outcome = NodeOutcome.SUCCESS
            node.completed_at = changed_at
            execution.status = definition.terminal_status or WorkflowStatus.FAILED
            execution.completed_at = changed_at
            if execution.status is WorkflowStatus.FAILED:
                execution.failure_reason = f"workflow reached failure terminal: {node_key}"
        self._touch(execution, changed_at)

    def _fail(self, execution: WorkflowExecution, reason: str, changed_at: datetime) -> None:
        execution.status = WorkflowStatus.FAILED
        execution.failure_reason = reason
        execution.completed_at = changed_at
        self._touch(execution, changed_at)

    @staticmethod
    def _node_execution(execution: WorkflowExecution, node_key: str) -> NodeExecution:
        try:
            return execution.nodes[node_key]
        except KeyError as exc:
            raise WorkflowExecutionError(f"unknown workflow node: {node_key}") from exc

    @staticmethod
    def _touch(execution: WorkflowExecution, changed_at: datetime) -> None:
        execution.updated_at = changed_at
        execution.version += 1
