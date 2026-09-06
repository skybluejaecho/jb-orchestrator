import asyncio

from jb_orchestrator.application import WorkerPresenceService
from jb_orchestrator.worker_presence import WorkerKind, WorkerLifecycleStatus
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
