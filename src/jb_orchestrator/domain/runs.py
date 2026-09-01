"""Run aggregate and lifecycle state machine."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition


class RunStatus(StrEnum):
    """Durable states for one execution of a user request."""

    QUEUED = "queued"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: Final[frozenset[RunStatus]] = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)

ALLOWED_RUN_TRANSITIONS: Final[dict[RunStatus, frozenset[RunStatus]]] = {
    RunStatus.QUEUED: frozenset({RunStatus.PLANNING, RunStatus.CANCELLED}),
    RunStatus.PLANNING: frozenset(
        {
            RunStatus.AWAITING_APPROVAL,
            RunStatus.READY,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.AWAITING_APPROVAL: frozenset({RunStatus.READY, RunStatus.CANCELLED}),
    RunStatus.READY: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.VERIFYING, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.VERIFYING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True, kw_only=True)
class Run:
    """One reproducible attempt to fulfill a user request."""

    request_id: UUID
    attempt: int = 1
    id: UUID = field(default_factory=uuid4)
    status: RunStatus = RunStatus.QUEUED
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise DomainValidationError("run attempt must be greater than zero")

    @property
    def is_terminal(self) -> bool:
        """Return whether no further transitions are permitted."""

        return self.status in TERMINAL_RUN_STATUSES

    def transition_to(self, target: RunStatus, *, at: datetime | None = None) -> None:
        """Move this run to an allowed lifecycle state."""

        if target not in ALLOWED_RUN_TRANSITIONS[self.status]:
            raise InvalidStateTransition(f"cannot transition run from {self.status} to {target}")

        changed_at = at or datetime.now(UTC)
        self.status = target
        self.updated_at = changed_at
        self.version += 1

        if target is RunStatus.RUNNING and self.started_at is None:
            self.started_at = changed_at
        if target in TERMINAL_RUN_STATUSES:
            self.completed_at = changed_at

    def fail(self, reason: str, *, at: datetime | None = None) -> None:
        """Move to FAILED while retaining a human-readable cause."""

        reason = reason.strip()
        if not reason:
            raise DomainValidationError("failure reason must not be empty")
        self.transition_to(RunStatus.FAILED, at=at)
        self.failure_reason = reason
