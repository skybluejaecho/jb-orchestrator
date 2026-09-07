"""Server-side polling runtime for durable worker-readiness evaluation."""

import asyncio
import logging

from jb_orchestrator.application.worker_readiness_services import (
    WorkerReadinessEvaluationBatch,
    WorkerReadinessService,
)
from jb_orchestrator.domain import Project

logger = logging.getLogger(__name__)


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
        self._cursor: Project | None = None
        self.last_cycle: WorkerReadinessEvaluationBatch | None = None

    async def run_once(self) -> int:
        batch = await self._service.evaluate_active_project_batch(
            stale_after_seconds=self._stale_after_seconds,
            critical_after_seconds=self._critical_after_seconds,
            after=self._cursor,
            limit=self._project_limit,
        )
        self._cursor = batch.next_cursor
        self.last_cycle = batch
        for failure in batch.failures:
            logger.error(
                "Worker-readiness project evaluation failed",
                extra={
                    "project_id": str(failure.project_id),
                    "error_type": failure.error_type,
                    "error_message": failure.message,
                },
            )
        logger.info(
            "Worker-readiness evaluation cycle completed",
            extra={
                "attempted_count": batch.attempted_count,
                "succeeded_count": len(batch.reports),
                "failed_count": len(batch.failures),
                "has_next_page": batch.next_cursor is not None,
            },
        )
        return len(batch.reports)

    async def run(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._poll_interval_seconds)
