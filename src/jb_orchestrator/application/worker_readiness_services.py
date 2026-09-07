"""Project-scoped diagnostics for READY tasks and worker capabilities."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.notification_services import enqueue_notification_deliveries
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent, Project, ProjectStatus
from jb_orchestrator.worker_presence import (
    ProjectWorkerReadiness,
    WorkerCapabilityCoverage,
    WorkerInstance,
    WorkerKind,
    WorkerObservedStatus,
    WorkerReadinessAlert,
    WorkerReadinessAlertStatus,
    WorkerReadinessIssue,
    WorkerReadinessIssueReason,
)
from jb_orchestrator.workflows import NodeExecutionStatus, WorkflowStatus


@dataclass(frozen=True, slots=True)
class WorkerReadinessEvaluationFailure:
    project_id: UUID
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class WorkerReadinessEvaluationBatch:
    reports: tuple[ProjectWorkerReadiness, ...]
    failures: tuple[WorkerReadinessEvaluationFailure, ...]
    attempted_count: int
    next_cursor: Project | None


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
            return await self._inspect_project(
                unit_of_work,
                project_id,
                stale_after_seconds=stale_after_seconds,
                checked_at=checked_at,
            )

    async def evaluate_project(
        self,
        project_id: UUID,
        *,
        stale_after_seconds: float = 90.0,
        critical_after_seconds: float = 300.0,
        at: datetime | None = None,
    ) -> ProjectWorkerReadiness:
        checked_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            acquired = (
                await unit_of_work.worker_readiness_alerts.try_acquire_project_evaluation_lock(
                    project_id
                )
            )
            report = await self._inspect_project(
                unit_of_work,
                project_id,
                stale_after_seconds=stale_after_seconds,
                checked_at=checked_at,
            )
            if not acquired:
                return report
            current_occurrences = {
                (issue.workflow_execution_id, issue.node_key, issue.ready_since)
                for issue in report.issues
            }
            for issue in report.issues:
                alert = await unit_of_work.worker_readiness_alerts.get_occurrence(
                    workflow_execution_id=issue.workflow_execution_id,
                    node_key=issue.node_key,
                    ready_since=issue.ready_since,
                    for_update=True,
                )
                if alert is None:
                    alert = WorkerReadinessAlert(
                        project_id=project_id,
                        workflow_execution_id=issue.workflow_execution_id,
                        run_id=issue.run_id,
                        node_key=issue.node_key,
                        executor_key=issue.executor_key,
                        ready_since=issue.ready_since,
                        reason=issue.reason,
                        first_detected_at=checked_at,
                        last_observed_at=checked_at,
                    )
                    await unit_of_work.worker_readiness_alerts.add(alert)
                    await self._append_alert_event(unit_of_work, alert, "worker.readiness_alerted")
                else:
                    reason_changed = alert.observe(issue.reason, at=checked_at)
                    escalated = alert.escalate(
                        critical_after_seconds=critical_after_seconds,
                        at=checked_at,
                    )
                    await unit_of_work.worker_readiness_alerts.save(alert)
                    if reason_changed:
                        await self._append_alert_event(
                            unit_of_work, alert, "worker.readiness_alert_reason_changed"
                        )
                    if escalated:
                        await self._append_alert_event(
                            unit_of_work, alert, "worker.readiness_critical"
                        )

            active_alerts = await unit_of_work.worker_readiness_alerts.list_by_project(
                project_id,
                status=WorkerReadinessAlertStatus.ACTIVE,
                limit=500,
            )
            for alert in active_alerts:
                occurrence = (
                    alert.workflow_execution_id,
                    alert.node_key,
                    alert.ready_since,
                )
                if occurrence in current_occurrences:
                    continue
                alert.resolve(at=checked_at)
                await unit_of_work.worker_readiness_alerts.save(alert)
                await self._append_alert_event(unit_of_work, alert, "worker.readiness_resolved")
            final_report = await self._inspect_project(
                unit_of_work,
                project_id,
                stale_after_seconds=stale_after_seconds,
                checked_at=checked_at,
            )
            await unit_of_work.commit()
            return final_report

    async def evaluate_active_projects(
        self,
        *,
        stale_after_seconds: float = 90.0,
        critical_after_seconds: float = 300.0,
        limit: int = 100,
        at: datetime | None = None,
    ) -> tuple[ProjectWorkerReadiness, ...]:
        batch = await self.evaluate_active_project_batch(
            stale_after_seconds=stale_after_seconds,
            critical_after_seconds=critical_after_seconds,
            limit=limit,
            at=at,
        )
        return batch.reports

    async def evaluate_active_project_batch(
        self,
        *,
        stale_after_seconds: float = 90.0,
        critical_after_seconds: float = 300.0,
        after: Project | None = None,
        limit: int = 100,
        at: datetime | None = None,
    ) -> WorkerReadinessEvaluationBatch:
        if limit <= 0:
            raise ValueError("worker readiness project limit must be positive")
        async with self._unit_of_work_factory() as unit_of_work:
            candidates = await unit_of_work.projects.list(
                status=ProjectStatus.ACTIVE,
                after=after,
                limit=limit + 1,
            )
        projects = candidates[:limit]
        reports: list[ProjectWorkerReadiness] = []
        failures: list[WorkerReadinessEvaluationFailure] = []
        for project in projects:
            try:
                reports.append(
                    await self.evaluate_project(
                        project.id,
                        stale_after_seconds=stale_after_seconds,
                        critical_after_seconds=critical_after_seconds,
                        at=at,
                    )
                )
            except Exception as exc:
                failures.append(
                    WorkerReadinessEvaluationFailure(
                        project_id=project.id,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
        return WorkerReadinessEvaluationBatch(
            reports=tuple(reports),
            failures=tuple(failures),
            attempted_count=len(projects),
            next_cursor=projects[-1] if len(candidates) > limit else None,
        )

    async def _inspect_project(
        self,
        unit_of_work: UnitOfWork,
        project_id: UUID,
        *,
        stale_after_seconds: float,
        checked_at: datetime,
    ) -> ProjectWorkerReadiness:
        if await unit_of_work.projects.get(project_id) is None:
            raise ResourceNotFound(f"project not found: {project_id}")
        executions = await unit_of_work.workflow_executions.list_by_project(
            project_id,
            status=WorkflowStatus.RUNNING,
            limit=500,
        )
        workers = await unit_of_work.worker_instances.list(limit=1000)
        alerts = await unit_of_work.worker_readiness_alerts.list_by_project(project_id, limit=500)

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
            alerts=tuple(alerts),
        )

    @staticmethod
    async def _append_alert_event(
        unit_of_work: UnitOfWork, alert: WorkerReadinessAlert, event_type: str
    ) -> None:
        event = DomainEvent(
            aggregate_type="project",
            aggregate_id=alert.project_id,
            event_type=event_type,
            payload={
                "alert_id": str(alert.id),
                "workflow_execution_id": str(alert.workflow_execution_id),
                "run_id": str(alert.run_id),
                "node_key": alert.node_key,
                "executor_key": alert.executor_key,
                "reason": alert.reason.value,
                "status": alert.status.value,
                "critical_at": alert.critical_at.isoformat() if alert.critical_at else None,
            },
        )
        await unit_of_work.events.append(event)
        await enqueue_notification_deliveries(unit_of_work, event)

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
