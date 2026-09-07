"""Persistence ports for worker process presence and readiness alerts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from jb_orchestrator.worker_presence.models import WorkerInstance, WorkerLifecycleStatus
from jb_orchestrator.worker_presence.readiness import (
    WorkerReadinessAlert,
    WorkerReadinessAlertStatus,
)


class WorkerInstanceRepository(Protocol):
    async def add(self, worker: WorkerInstance) -> None: ...

    async def get(
        self, instance_id: UUID, *, for_update: bool = False
    ) -> WorkerInstance | None: ...

    async def list(
        self, *, status: WorkerLifecycleStatus | None = None, limit: int = 100
    ) -> list[WorkerInstance]: ...

    async def save(self, worker: WorkerInstance) -> None: ...


class WorkerReadinessAlertRepository(Protocol):
    async def try_acquire_project_evaluation_lock(self, project_id: UUID) -> bool: ...

    async def add(self, alert: WorkerReadinessAlert) -> None: ...

    async def get_occurrence(
        self,
        *,
        workflow_execution_id: UUID,
        node_key: str,
        ready_since: datetime,
        for_update: bool = False,
    ) -> WorkerReadinessAlert | None: ...

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: WorkerReadinessAlertStatus | None = None,
        limit: int = 500,
    ) -> list[WorkerReadinessAlert]: ...

    async def save(self, alert: WorkerReadinessAlert) -> None: ...
