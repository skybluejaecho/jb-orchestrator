"""Read models explaining whether READY workflow tasks can be claimed."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class WorkerReadinessIssueReason(StrEnum):
    NO_CAPABLE_WORKER = "no_capable_worker"
    CAPABLE_WORKERS_OFFLINE = "capable_workers_offline"


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
