"""Worker process entry point."""

import asyncio
import os
import socket

import typer

from jb_orchestrator.application import BudgetService, TaskDispatchService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.skills import SkillSourceKind
from jb_orchestrator.skills.materialization import (
    ArchiveSkillFetcher,
    GitSkillFetcher,
    LocalSkillFetcher,
    SkillMaterializer,
)
from jb_orchestrator.worker.registry import ExecutorRegistrationError, ExecutorRegistry
from jb_orchestrator.worker.runtime import WorkerRuntime

app = typer.Typer(add_completion=False, invoke_without_command=True)


async def run_until_stopped(runtime: WorkerRuntime) -> None:
    """Create loop-bound shutdown state and run continuously."""

    await runtime.run(asyncio.Event())


@app.callback()
def run(
    *,
    once: bool = typer.Option(False, help="Poll once and exit."),
    list_executors: bool = typer.Option(False, help="List installed executor adapters and exit."),
    worker_id: str | None = typer.Option(None, help="Stable worker identity."),
    poll_interval: float = typer.Option(1.0, min=0.1, help="Idle polling interval in seconds."),
) -> None:
    """Start a worker using installed jb_orchestrator.executors entry points."""

    try:
        registry = ExecutorRegistry.from_entry_points()
    except ExecutorRegistrationError as exc:
        typer.echo(f"Executor discovery failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if list_executors:
        keys = sorted(registry.supported_keys)
        typer.echo("\n".join(keys) if keys else "No executor adapters installed.")
        return
    if not registry.supported_keys:
        typer.echo(
            "No executor adapters installed in the jb_orchestrator.executors entry-point group.",
            err=True,
        )
        raise typer.Exit(code=2)

    resolved_worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    settings = get_settings()
    session_factory = create_session_factory(settings)
    dispatch = TaskDispatchService(lambda: SqlAlchemyUnitOfWork(session_factory))
    runtime = WorkerRuntime(
        resolved_worker_id,
        dispatch,
        registry,
        poll_interval_seconds=poll_interval,
        heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
        cancellation_timeout_seconds=settings.worker_cancellation_timeout_seconds,
        skill_materializer=SkillMaterializer(
            settings.skill_cache_dir,
            {
                SkillSourceKind.LOCAL: LocalSkillFetcher(settings.skill_local_root),
                SkillSourceKind.GIT: GitSkillFetcher(settings.skill_allowed_remote_hosts),
                SkillSourceKind.ARCHIVE: ArchiveSkillFetcher(
                    settings.skill_local_root,
                    allowed_remote_hosts=settings.skill_allowed_remote_hosts,
                ),
            },
        ),
        budget_service=BudgetService(lambda: SqlAlchemyUnitOfWork(session_factory)),
    )
    if once:
        worked = asyncio.run(runtime.run_once())
        typer.echo("Task processed." if worked else "No supported READY task found.")
        return

    try:
        asyncio.run(run_until_stopped(runtime))
    except KeyboardInterrupt:
        typer.echo("Worker stopped.")


def main() -> None:
    """Invoke the worker application."""

    app()


if __name__ == "__main__":
    main()
