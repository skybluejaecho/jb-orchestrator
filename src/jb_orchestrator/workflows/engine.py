"""Deterministic workflow state transition engine."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

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

    def claim_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        *,
        worker_id: str,
        lease_seconds: int,
        lease_token: UUID | None = None,
        at: datetime | None = None,
    ) -> NodeExecution:
        """Begin a task and attach an expiring ownership lease."""

        if not worker_id.strip():
            raise WorkflowExecutionError("worker_id must not be empty")
        if lease_seconds < 1:
            raise WorkflowExecutionError("lease_seconds must be greater than zero")
        changed_at = at or datetime.now(UTC)
        node = self.begin_task(execution, node_key, at=changed_at)
        node.worker_id = worker_id
        node.lease_token = lease_token or uuid4()
        node.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        return node

    def renew_lease(
        self,
        execution: WorkflowExecution,
        node_key: str,
        lease_token: UUID,
        *,
        lease_seconds: int,
        at: datetime | None = None,
    ) -> None:
        if lease_seconds < 1:
            raise WorkflowExecutionError("lease_seconds must be greater than zero")
        changed_at = at or datetime.now(UTC)
        node = self._owned_running_node(execution, node_key, lease_token, changed_at)
        node.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        node.updated_at = changed_at
        self._touch(execution, changed_at)

    def complete_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        outcome: NodeOutcome,
        *,
        output: dict[str, Any] | None = None,
        lease_token: UUID | None = None,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        if node.status is not NodeExecutionStatus.RUNNING:
            raise WorkflowExecutionError("only a running task node can complete")
        if outcome not in {NodeOutcome.SUCCESS, NodeOutcome.FAILURE}:
            raise WorkflowExecutionError("task nodes require success or failure outcome")
        changed_at = at or datetime.now(UTC)
        self._validate_optional_lease(node, lease_token, changed_at)
        node.status = NodeExecutionStatus.SUCCEEDED
        node.outcome = outcome
        node.output = output
        node.completed_at = changed_at
        node.updated_at = changed_at
        self._clear_lease(node)
        self._touch(execution, changed_at)
        self._route(execution, node_key, outcome, changed_at)

    def fail_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        reason: str,
        *,
        lease_token: UUID | None = None,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        if node.status is not NodeExecutionStatus.RUNNING:
            raise WorkflowExecutionError("only a running task node can fail")
        changed_at = at or datetime.now(UTC)
        self._validate_optional_lease(node, lease_token, changed_at)
        self._handle_task_failure(execution, node, reason, changed_at)

    def expire_task(
        self,
        execution: WorkflowExecution,
        node_key: str,
        *,
        at: datetime | None = None,
    ) -> None:
        node = self._node_execution(execution, node_key)
        changed_at = at or datetime.now(UTC)
        if node.status is not NodeExecutionStatus.RUNNING or node.lease_expires_at is None:
            raise WorkflowExecutionError("node has no active lease")
        if self._as_utc(node.lease_expires_at) > self._as_utc(changed_at):
            raise WorkflowExecutionError("node lease has not expired")
        self._handle_task_failure(execution, node, "task lease expired", changed_at)

    def _handle_task_failure(
        self,
        execution: WorkflowExecution,
        node: NodeExecution,
        reason: str,
        changed_at: datetime,
    ) -> None:
        definition = execution.snapshot.node(node.node_key)
        self._clear_lease(node)
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
                self._clear_lease(node)
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
        self._clear_lease(node)
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
    def _validate_optional_lease(
        node: NodeExecution, lease_token: UUID | None, changed_at: datetime
    ) -> None:
        if node.lease_token is None:
            if lease_token is not None:
                raise WorkflowExecutionError("node is not leased")
            return
        if lease_token != node.lease_token:
            raise WorkflowExecutionError("task lease token does not match")
        if node.lease_expires_at is None or WorkflowEngine._as_utc(
            node.lease_expires_at
        ) <= WorkflowEngine._as_utc(changed_at):
            raise WorkflowExecutionError("task lease has expired")

    @classmethod
    def _owned_running_node(
        cls,
        execution: WorkflowExecution,
        node_key: str,
        lease_token: UUID,
        changed_at: datetime,
    ) -> NodeExecution:
        node = cls._node_execution(execution, node_key)
        if node.status is not NodeExecutionStatus.RUNNING:
            raise WorkflowExecutionError("only a running task node can renew a lease")
        cls._validate_optional_lease(node, lease_token, changed_at)
        return node

    @staticmethod
    def _clear_lease(node: NodeExecution) -> None:
        node.worker_id = None
        node.lease_token = None
        node.lease_expires_at = None

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _touch(execution: WorkflowExecution, changed_at: datetime) -> None:
        execution.updated_at = changed_at
        execution.version += 1
