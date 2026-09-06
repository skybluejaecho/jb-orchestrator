"""Project-scoped diagnostics for READY tasks and worker capabilities."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.worker_presence import (
    ProjectWorkerReadiness,
    WorkerCapabilityCoverage,
    WorkerInstance,
    WorkerKind,
    WorkerObservedStatus,
    WorkerReadinessIssue,
    WorkerReadinessIssueReason,
)
from jb_orchestrator.workflows import NodeExecutionStatus, WorkflowStatus


class WorkerReadinessService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def inspect_project(
        self,
        project_id: UUID,
        *,
        stale_after_seconds: float = 90.0,
        at: datetime | None = None,
    ) -> ProjectWorkerReadiness:
        checked_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            executions = await unit_of_work.workflow_executions.list_by_project(
                project_id,
                status=WorkflowStatus.RUNNING,
                limit=500,
            )
            workers = await unit_of_work.worker_instances.list(limit=1000)

        current_workers = self._latest_execution_workers(workers)
        ready_nodes = [
            (execution, node)
            for execution in executions
            for node in execution.nodes.values()
            if node.status is NodeExecutionStatus.READY
        ]
        executor_keys = sorted({node.executor_key for _, node in ready_nodes})
        coverage = tuple(
            self._coverage(
                executor_key,
                current_workers,
                stale_after_seconds=stale_after_seconds,
                at=checked_at,
            )
            for executor_key in executor_keys
        )
        coverage_by_key = {item.executor_key: item for item in coverage}
        issues = tuple(
            WorkerReadinessIssue(
                workflow_execution_id=execution.id,
                run_id=execution.snapshot.run_id,
                node_key=node.node_key,
                executor_key=node.executor_key,
                ready_since=node.updated_at,
                reason=(
                    WorkerReadinessIssueReason.CAPABLE_WORKERS_OFFLINE
                    if coverage_by_key[node.executor_key].stale_worker_ids
                    or coverage_by_key[node.executor_key].stopped_worker_ids
                    else WorkerReadinessIssueReason.NO_CAPABLE_WORKER
                ),
            )
            for execution, node in sorted(ready_nodes, key=lambda item: item[1].updated_at)
            if not coverage_by_key[node.executor_key].online_worker_ids
        )
        online_count = sum(
            worker.observed_status(stale_after_seconds=stale_after_seconds, at=checked_at)
            is WorkerObservedStatus.ONLINE
            for worker in current_workers
        )
        return ProjectWorkerReadiness(
            project_id=project_id,
            checked_at=checked_at,
            online_execution_workers=online_count,
            coverage=coverage,
            issues=issues,
        )

    @staticmethod
    def _latest_execution_workers(workers: list[WorkerInstance]) -> list[WorkerInstance]:
        latest: dict[str, WorkerInstance] = {}
        for worker in workers:
            if worker.kind is WorkerKind.EXECUTION and worker.worker_id not in latest:
                latest[worker.worker_id] = worker
        return list(latest.values())

    @staticmethod
    def _coverage(
        executor_key: str,
        workers: list[WorkerInstance],
        *,
        stale_after_seconds: float,
        at: datetime,
    ) -> WorkerCapabilityCoverage:
        by_status: dict[WorkerObservedStatus, list[str]] = {
            status: [] for status in WorkerObservedStatus
        }
        for worker in workers:
            if executor_key not in worker.capabilities:
                continue
            status = worker.observed_status(stale_after_seconds=stale_after_seconds, at=at)
            by_status[status].append(worker.worker_id)
        return WorkerCapabilityCoverage(
            executor_key=executor_key,
            online_worker_ids=tuple(sorted(by_status[WorkerObservedStatus.ONLINE])),
            stale_worker_ids=tuple(sorted(by_status[WorkerObservedStatus.STALE])),
            stopped_worker_ids=tuple(sorted(by_status[WorkerObservedStatus.STOPPED])),
        )
