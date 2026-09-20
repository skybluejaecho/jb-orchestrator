"""Durable requests for executor-owned workspace maintenance."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition


class WorkspaceOperationKind(StrEnum):
    INSPECT = "inspect"
    CLEANUP = "cleanup"


class WorkspaceOperationStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True, kw_only=True)
class WorkspaceOperation:
    """One idempotent workspace command routed to its filesystem scope."""

    external_execution_id: UUID
    kind: WorkspaceOperationKind
    target_ref: str
    workspace_scope: str
    idempotency_key: str
    requested_by: str
    id: UUID = field(default_factory=uuid4)
    status: WorkspaceOperationStatus = WorkspaceOperationStatus.PENDING
    worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.target_ref, "target_ref"),
            (self.workspace_scope, "workspace_scope"),
            (self.idempotency_key, "idempotency_key"),
            (self.requested_by, "requested_by"),
        ):
            if not value.strip():
                raise DomainValidationError(f"workspace operation {label} must not be empty")
        self.target_ref = self.target_ref.strip()
        self.workspace_scope = self.workspace_scope.strip()
        self.idempotency_key = self.idempotency_key.strip()
        self.requested_by = self.requested_by.strip()

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            WorkspaceOperationStatus.SUCCEEDED,
            WorkspaceOperationStatus.FAILED,
        }

    def claim(self, worker_id: str, *, lease_seconds: int, at: datetime | None = None) -> None:
        if self.is_terminal:
            raise InvalidStateTransition("terminal workspace operation cannot be claimed")
        if not worker_id.strip() or lease_seconds <= 0:
            raise DomainValidationError(
                "workspace operation claim requires worker and positive lease"
            )
        changed_at = at or datetime.now(UTC)
        self.status = WorkspaceOperationStatus.CLAIMED
        self.worker_id = worker_id.strip()
        self.lease_token = uuid4()
        self.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        self.updated_at = changed_at

    def succeed(
        self, lease_token: UUID, result: dict[str, Any], *, at: datetime | None = None
    ) -> None:
        self._require_claim(lease_token)
        changed_at = at or datetime.now(UTC)
        self.status = WorkspaceOperationStatus.SUCCEEDED
        self.result = result
        self.failure_reason = None
        self.lease_expires_at = None
        self.completed_at = changed_at
        self.updated_at = changed_at

    def fail(self, lease_token: UUID, reason: str, *, at: datetime | None = None) -> None:
        self._require_claim(lease_token)
        normalized = reason.strip()
        if not normalized:
            raise DomainValidationError("workspace operation failure reason must not be empty")
        changed_at = at or datetime.now(UTC)
        self.status = WorkspaceOperationStatus.FAILED
        self.failure_reason = normalized
        self.lease_expires_at = None
        self.completed_at = changed_at
        self.updated_at = changed_at

    def _require_claim(self, lease_token: UUID) -> None:
        if self.status is not WorkspaceOperationStatus.CLAIMED or self.lease_token != lease_token:
            raise InvalidStateTransition("workspace operation lease is not owned by this worker")
