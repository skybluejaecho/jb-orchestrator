import asyncio

from jb_orchestrator.application import WorkerPresenceService, WorkerReadinessService
from jb_orchestrator.domain import Project
from jb_orchestrator.worker_presence import WorkerKind, WorkerLifecycleStatus
from jb_orchestrator.worker_presence.monitor import WorkerReadinessMonitorRuntime
from jb_orchestrator.worker_presence.runtime import WorkerPresenceRuntime
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_presence_runtime_heartbeats_and_stops_around_operation() -> None:
    store = MemoryStore()
    runtime = WorkerPresenceRuntime(
        WorkerPresenceService(lambda: MemoryUnitOfWork(store)),
        worker_id="worker-a",
        kind=WorkerKind.SCM,
        hostname="host-a",
        process_id=42,
        capabilities=("github",),
        workspace_scope="git-worktree:scope-a",
        heartbeat_interval_seconds=0.01,
    )

    async def operation() -> str:
        await asyncio.sleep(0.03)
        return "done"

    assert await runtime.run(operation) == "done"
    [worker] = store.worker_instances.values()
    assert worker.status is WorkerLifecycleStatus.STOPPED
    assert worker.last_seen_at > worker.started_at
    assert worker.workspace_scope == "git-worktree:scope-a"


async def test_readiness_monitor_evaluates_active_projects_once() -> None:
    store = MemoryStore()
    project = Project(
        key="monitor-project",
        name="Monitor Project",
        repository_url="https://github.com/example/monitor.git",
    )
    store.projects[project.id] = project
    runtime = WorkerReadinessMonitorRuntime(
        WorkerReadinessService(lambda: MemoryUnitOfWork(store)),
        poll_interval_seconds=1,
    )

    assert await runtime.run_once() == 1
