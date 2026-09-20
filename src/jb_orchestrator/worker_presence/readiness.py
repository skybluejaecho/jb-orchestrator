"""Read models explaining whether READY workflow tasks can be claimed."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
    critical_at: datetime | None = None
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

    def escalate(self, *, critical_after_seconds: float, at: datetime) -> bool:
        if critical_after_seconds <= 0:
            raise ValueError("worker readiness critical threshold must be positive")
        if self.status is not WorkerReadinessAlertStatus.ACTIVE or self.critical_at is not None:
            return False
        if _as_utc(at) - _as_utc(self.first_detected_at) < timedelta(
            seconds=critical_after_seconds
        ):
            return False
        self.critical_at = at
        return True


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
