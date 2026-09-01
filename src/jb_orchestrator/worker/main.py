"""Worker process entry point."""

import asyncio
import os
import socket

import typer

from jb_orchestrator.application import TaskDispatchService
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
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
    session_factory = create_session_factory()
    dispatch = TaskDispatchService(lambda: SqlAlchemyUnitOfWork(session_factory))
    runtime = WorkerRuntime(
        resolved_worker_id,
        dispatch,
        registry,
        poll_interval_seconds=poll_interval,
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
