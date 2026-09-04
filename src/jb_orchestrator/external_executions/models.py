"""External execution lifecycle model."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition


class ExternalExecutionStatus(StrEnum):
    STARTING = "starting"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_EXTERNAL_STATUSES = frozenset(
    {
        ExternalExecutionStatus.SUCCEEDED,
        ExternalExecutionStatus.FAILED,
        ExternalExecutionStatus.CANCELLED,
    }
)


@dataclass(slots=True, kw_only=True)
class ExternalExecution:
    """A retry-safe mapping from one logical JB task visit to an external run."""

    execution_id: UUID
    run_id: UUID
    node_key: str
    executor_key: str
    idempotency_key: str
    external_session_key: str
    external_agent_id: str | None = None
    workspace_path: str | None = None
    workspace_repository_path: str | None = None
    workspace_branch: str | None = None
    workspace_base_ref: str | None = None
    workspace_released_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    external_run_id: str | None = None
    status: ExternalExecutionStatus = ExternalExecutionStatus.STARTING
    terminal_result: dict[str, Any] | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        required = (
            self.node_key,
            self.executor_key,
            self.idempotency_key,
            self.external_session_key,
        )
        if any(not value.strip() for value in required):
            raise DomainValidationError("external execution keys must not be empty")
        if self.status is ExternalExecutionStatus.ACTIVE and not self.external_run_id:
            raise DomainValidationError("active external execution requires external_run_id")
        workspace_values = (
            self.workspace_path,
            self.workspace_branch,
            self.workspace_base_ref,
        )
        if any(workspace_values) and not all(
            isinstance(value, str) and value.strip() for value in workspace_values
        ):
            raise DomainValidationError(
                "external execution workspace metadata must be complete or omitted"
            )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_EXTERNAL_STATUSES

    def release_workspace(self, *, at: datetime | None = None) -> None:
        if not self.is_terminal:
            raise InvalidStateTransition("cannot release workspace before external execution ends")
        if not self.workspace_path:
            raise DomainValidationError("external execution has no workspace to release")
        if self.workspace_released_at is not None:
            return
        changed_at = at or datetime.now(UTC)
        self.workspace_released_at = changed_at
        self.updated_at = changed_at

    def accept(self, external_run_id: str, *, at: datetime | None = None) -> None:
        if self.is_terminal:
            raise InvalidStateTransition(f"cannot accept external execution from {self.status}")
        normalized = external_run_id.strip()
        if not normalized:
            raise DomainValidationError("external_run_id must not be empty")
        if self.external_run_id is not None and self.external_run_id != normalized:
            raise DomainValidationError("external_run_id cannot change")
        self.external_run_id = normalized
        self.status = ExternalExecutionStatus.ACTIVE
        self.updated_at = at or datetime.now(UTC)

    def finish(
        self,
        status: ExternalExecutionStatus,
        *,
        terminal_result: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        at: datetime | None = None,
    ) -> None:
        if status not in TERMINAL_EXTERNAL_STATUSES:
            raise DomainValidationError("external execution finish status must be terminal")
        if self.is_terminal:
            if self.status is status:
                return
            raise InvalidStateTransition(f"cannot finish external execution from {self.status}")
        changed_at = at or datetime.now(UTC)
        self.status = status
        self.terminal_result = terminal_result
        self.failure_reason = failure_reason
        self.updated_at = changed_at
        self.completed_at = changed_at
