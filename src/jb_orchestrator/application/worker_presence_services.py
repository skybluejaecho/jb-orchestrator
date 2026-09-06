"""Application service for durable worker process presence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.worker_presence import (
    WorkerInstance,
    WorkerKind,
    WorkerObservedStatus,
)


@dataclass(frozen=True, slots=True)
class WorkerPresenceView:
    worker: WorkerInstance
    observed_status: WorkerObservedStatus


class WorkerPresenceService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def register(
        self,
        *,
        worker_id: str,
        kind: WorkerKind,
        hostname: str,
        process_id: int,
        capabilities: tuple[str, ...],
        workspace_scope: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerInstance:
        worker = WorkerInstance(
            worker_id=worker_id,
            kind=kind,
            hostname=hostname,
            process_id=process_id,
            capabilities=capabilities,
            workspace_scope=workspace_scope,
            metadata=metadata or {},
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.worker_instances.add(worker)
            await unit_of_work.commit()
        return worker

    async def heartbeat(self, instance_id: UUID, *, at: datetime | None = None) -> WorkerInstance:
        async with self._unit_of_work_factory() as unit_of_work:
            worker = await unit_of_work.worker_instances.get(instance_id, for_update=True)
            if worker is None:
                raise ResourceNotFound(f"worker instance not found: {instance_id}")
            worker.heartbeat(at=at)
            await unit_of_work.worker_instances.save(worker)
            await unit_of_work.commit()
            return worker

    async def stop(self, instance_id: UUID, *, at: datetime | None = None) -> WorkerInstance:
        async with self._unit_of_work_factory() as unit_of_work:
            worker = await unit_of_work.worker_instances.get(instance_id, for_update=True)
            if worker is None:
                raise ResourceNotFound(f"worker instance not found: {instance_id}")
            worker.stop(at=at)
            await unit_of_work.worker_instances.save(worker)
            await unit_of_work.commit()
            return worker

    async def list(
        self,
        *,
        limit: int = 100,
        stale_after_seconds: float = 90.0,
        at: datetime | None = None,
    ) -> list[WorkerPresenceView]:
        async with self._unit_of_work_factory() as unit_of_work:
            workers = await unit_of_work.worker_instances.list(limit=limit)
        return [
            WorkerPresenceView(
                worker=worker,
                observed_status=worker.observed_status(
                    stale_after_seconds=stale_after_seconds, at=at
                ),
            )
            for worker in workers
        ]
