"""Read models explaining whether READY workflow tasks can be claimed."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class WorkerReadinessIssueReason(StrEnum):
    NO_CAPABLE_WORKER = "no_capable_worker"
    CAPABLE_WORKERS_OFFLINE = "capable_workers_offline"


class WorkerReadinessAlertStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


@dataclass(slots=True, kw_only=True)
class WorkerReadinessAlert:
    project_id: UUID
    workflow_execution_id: UUID
    run_id: UUID
    node_key: str
    executor_key: str
    ready_since: datetime
    reason: WorkerReadinessIssueReason
    id: UUID = field(default_factory=uuid4)
    status: WorkerReadinessAlertStatus = WorkerReadinessAlertStatus.ACTIVE
    first_detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    def observe(self, reason: WorkerReadinessIssueReason, *, at: datetime) -> bool:
        changed = self.reason is not reason
        self.reason = reason
        self.last_observed_at = at
        return changed

    def resolve(self, *, at: datetime) -> None:
        if self.status is WorkerReadinessAlertStatus.RESOLVED:
            return
        self.status = WorkerReadinessAlertStatus.RESOLVED
        self.last_observed_at = at
        self.resolved_at = at


@dataclass(frozen=True, slots=True)
class WorkerCapabilityCoverage:
    executor_key: str
    online_worker_ids: tuple[str, ...]
    stale_worker_ids: tuple[str, ...]
    stopped_worker_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkerReadinessIssue:
    workflow_execution_id: UUID
    run_id: UUID
    node_key: str
    executor_key: str
    ready_since: datetime
    reason: WorkerReadinessIssueReason


@dataclass(frozen=True, slots=True)
class ProjectWorkerReadiness:
    project_id: UUID
    checked_at: datetime
    online_execution_workers: int
    coverage: tuple[WorkerCapabilityCoverage, ...]
    issues: tuple[WorkerReadinessIssue, ...]
    alerts: tuple[WorkerReadinessAlert, ...] = ()
