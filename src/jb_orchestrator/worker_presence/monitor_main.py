"""Worker-readiness monitor process entry point."""

import asyncio
import os
import socket

import typer

from jb_orchestrator.application import WorkerPresenceService, WorkerReadinessService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.worker_presence import WorkerKind
from jb_orchestrator.worker_presence.monitor import WorkerReadinessMonitorRuntime
from jb_orchestrator.worker_presence.runtime import WorkerPresenceRuntime

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def run(
    *,
    once: bool = typer.Option(False, help="Evaluate active projects once and exit."),
    worker_id: str | None = typer.Option(None, help="Stable readiness monitor identity."),
    poll_interval: float | None = typer.Option(
        None, min=0.1, help="Evaluation interval in seconds."
    ),
    project_limit: int | None = typer.Option(
        None, min=1, help="Maximum active projects evaluated per cycle."
    ),
) -> None:
    """Continuously evaluate Worker readiness independently from Jarvis."""

    settings = get_settings()
    session_factory = create_session_factory(settings)
    uow = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    resolved_worker_id = worker_id or f"{socket.gethostname()}-readiness-{os.getpid()}"
    runtime = WorkerReadinessMonitorRuntime(
        WorkerReadinessService(uow),
        poll_interval_seconds=poll_interval or settings.worker_readiness_poll_interval_seconds,
        stale_after_seconds=settings.worker_presence_stale_after_seconds,
        critical_after_seconds=settings.worker_readiness_alert_critical_after_seconds,
        project_limit=project_limit or settings.worker_readiness_project_limit,
    )
    presence = WorkerPresenceRuntime(
        WorkerPresenceService(uow),
        worker_id=resolved_worker_id,
        kind=WorkerKind.READINESS_MONITOR,
        hostname=socket.gethostname(),
        process_id=os.getpid(),
        capabilities=("worker-readiness",),
        heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
    )
    if once:
        count = asyncio.run(presence.run(runtime.run_once))
        typer.echo(f"Evaluated {count} active project(s).")
        return
    try:
        asyncio.run(presence.run(runtime.run))
    except KeyboardInterrupt:
        typer.echo("Worker-readiness monitor stopped.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
