"""Durable process presence for orchestration workers."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError


class WorkerKind(StrEnum):
    EXECUTION = "execution"
    WORKSPACE = "workspace"
    SCM = "scm"
    READINESS_MONITOR = "readiness_monitor"


class WorkerLifecycleStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"


class WorkerObservedStatus(StrEnum):
    ONLINE = "online"
    STALE = "stale"
    STOPPED = "stopped"


@dataclass(slots=True, kw_only=True)
class WorkerInstance:
    worker_id: str
    kind: WorkerKind
    hostname: str
    process_id: int
    capabilities: tuple[str, ...]
    workspace_scope: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    status: WorkerLifecycleStatus = WorkerLifecycleStatus.RUNNING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stopped_at: datetime | None = None

    def __post_init__(self) -> None:
        self.worker_id = self.worker_id.strip()
        self.hostname = self.hostname.strip()
        self.capabilities = tuple(
            sorted({value.strip() for value in self.capabilities if value.strip()})
        )
        self.workspace_scope = self.workspace_scope.strip() if self.workspace_scope else None
        if not self.worker_id or not self.hostname:
            raise DomainValidationError("worker identity and hostname must not be empty")
        if self.process_id <= 0:
            raise DomainValidationError("worker process_id must be positive")
        if not self.capabilities:
            raise DomainValidationError("worker requires at least one capability")

    def heartbeat(self, *, at: datetime | None = None) -> None:
        if self.status is WorkerLifecycleStatus.STOPPED:
            raise DomainValidationError("stopped worker cannot heartbeat")
        self.last_seen_at = at or datetime.now(UTC)

    def stop(self, *, at: datetime | None = None) -> None:
        if self.status is WorkerLifecycleStatus.STOPPED:
            return
        changed_at = at or datetime.now(UTC)
        self.status = WorkerLifecycleStatus.STOPPED
        self.last_seen_at = changed_at
        self.stopped_at = changed_at

    def observed_status(
        self, *, stale_after_seconds: float, at: datetime | None = None
    ) -> WorkerObservedStatus:
        if stale_after_seconds <= 0:
            raise DomainValidationError("worker stale threshold must be positive")
        if self.status is WorkerLifecycleStatus.STOPPED:
            return WorkerObservedStatus.STOPPED
        observed_at = at or datetime.now(UTC)
        last_seen = (
            self.last_seen_at.replace(tzinfo=UTC)
            if self.last_seen_at.tzinfo is None
            else self.last_seen_at.astimezone(UTC)
        )
        current = (
            observed_at.replace(tzinfo=UTC)
            if observed_at.tzinfo is None
            else observed_at.astimezone(UTC)
        )
        if current - last_seen > timedelta(seconds=stale_after_seconds):
            return WorkerObservedStatus.STALE
        return WorkerObservedStatus.ONLINE
