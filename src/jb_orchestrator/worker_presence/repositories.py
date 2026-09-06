"""Persistence port for worker process presence."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.worker_presence.models import WorkerInstance


class WorkerInstanceRepository(Protocol):
    async def add(self, worker: WorkerInstance) -> None: ...

    async def get(
        self, instance_id: UUID, *, for_update: bool = False
    ) -> WorkerInstance | None: ...

    async def list(self, *, limit: int = 100) -> list[WorkerInstance]: ...

    async def save(self, worker: WorkerInstance) -> None: ...
