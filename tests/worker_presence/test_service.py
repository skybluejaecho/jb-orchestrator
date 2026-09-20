from datetime import UTC, datetime, timedelta

from jb_orchestrator.application import WorkerPresenceService
from jb_orchestrator.worker_presence import (
    WorkerKind,
    WorkerLifecycleStatus,
    WorkerObservedStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_worker_lifetime_is_registered_heartbeated_and_stopped() -> None:
    store = MemoryStore()
    service = WorkerPresenceService(lambda: MemoryUnitOfWork(store))
    started_at = datetime(2026, 9, 6, tzinfo=UTC)
    worker = await service.register(
        worker_id="host-a-execution-42",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=42,
        capabilities=("openclaw", "codex", "openclaw"),
    )
    worker.started_at = started_at
    worker.last_seen_at = started_at

    await service.heartbeat(worker.id, at=started_at + timedelta(seconds=30))
    [online] = await service.list(at=started_at + timedelta(seconds=89), stale_after_seconds=60)
    [stale] = await service.list(at=started_at + timedelta(seconds=91), stale_after_seconds=60)
    stopped = await service.stop(worker.id, at=started_at + timedelta(seconds=92))

    assert worker.capabilities == ("codex", "openclaw")
    assert online.observed_status is WorkerObservedStatus.ONLINE
    assert stale.observed_status is WorkerObservedStatus.STALE
    assert stopped.status is WorkerLifecycleStatus.STOPPED
    assert stopped.stopped_at == started_at + timedelta(seconds=92)
