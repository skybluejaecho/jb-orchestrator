"""Server-side polling runtime for durable worker-readiness evaluation."""

import asyncio

from jb_orchestrator.application.worker_readiness_services import WorkerReadinessService


class WorkerReadinessMonitorRuntime:
    def __init__(
        self,
        service: WorkerReadinessService,
        *,
        poll_interval_seconds: float = 30.0,
        stale_after_seconds: float = 90.0,
        critical_after_seconds: float = 300.0,
        project_limit: int = 100,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("worker readiness poll interval must be positive")
        if stale_after_seconds <= 0 or critical_after_seconds <= 0:
            raise ValueError("worker readiness thresholds must be positive")
        if project_limit <= 0:
            raise ValueError("worker readiness project limit must be positive")
        self._service = service
        self._poll_interval_seconds = poll_interval_seconds
        self._stale_after_seconds = stale_after_seconds
        self._critical_after_seconds = critical_after_seconds
        self._project_limit = project_limit

    async def run_once(self) -> int:
        reports = await self._service.evaluate_active_projects(
            stale_after_seconds=self._stale_after_seconds,
            critical_after_seconds=self._critical_after_seconds,
            limit=self._project_limit,
        )
        return len(reports)

    async def run(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._poll_interval_seconds)
