"""SCM publication worker process entry point."""

import asyncio
import os
import socket

import typer

from jb_orchestrator.application import (
    ExternalExecutionService,
    ScmPublicationService,
    WorkerPresenceService,
)
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.scm.registry import ScmPublisherRegistrationError, ScmPublisherRegistry
from jb_orchestrator.scm.runtime import ScmPublicationRuntime
from jb_orchestrator.worker_presence import WorkerKind
from jb_orchestrator.worker_presence.runtime import WorkerPresenceRuntime

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def run(
    *,
    workspace_scope: str | None = typer.Option(
        None, help="Opaque workspace scope served by this host."
    ),
    once: bool = typer.Option(False, help="Poll once and exit."),
    list_publishers: bool = typer.Option(
        False, help="List installed SCM publisher adapters and exit."
    ),
    worker_id: str | None = typer.Option(None, help="Stable publication worker identity."),
    poll_interval: float = typer.Option(1.0, min=0.1, help="Idle polling interval in seconds."),
    lease_seconds: int = typer.Option(300, min=2, help="Claim lease duration in seconds."),
    operation_timeout: float = typer.Option(
        240.0, min=1.0, help="Maximum provider operation duration in seconds."
    ),
    automatic_retry_limit: int = typer.Option(
        0,
        min=0,
        max=10,
        help="Automatic retries after the initial attempt; disabled by default.",
    ),
    automatic_retry_base_delay: float = typer.Option(
        30.0, min=0.1, help="Initial automatic retry delay in seconds."
    ),
    automatic_retry_max_delay: float = typer.Option(
        300.0, min=0.1, help="Maximum automatic retry delay in seconds."
    ),
) -> None:
    """Start a worker using installed jb_orchestrator.scm_publishers entry points."""

    try:
        registry = ScmPublisherRegistry.from_entry_points()
    except ScmPublisherRegistrationError as exc:
        typer.echo(f"SCM publisher discovery failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if list_publishers:
        keys = sorted(registry.supported_keys)
        typer.echo("\n".join(keys) if keys else "No SCM publisher adapters installed.")
        return
    if not registry.supported_keys:
        typer.echo(
            "No SCM publisher adapters installed in the "
            "jb_orchestrator.scm_publishers entry-point group.",
            err=True,
        )
        raise typer.Exit(code=2)
    if workspace_scope is None or not workspace_scope.strip():
        typer.echo("--workspace-scope is required when running the publication worker.", err=True)
        raise typer.Exit(code=2)

    settings = get_settings()
    session_factory = create_session_factory(settings)
    uow = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    resolved_worker_id = worker_id or f"{socket.gethostname()}-scm-{os.getpid()}"
    runtime = ScmPublicationRuntime(
        resolved_worker_id,
        workspace_scope,
        ScmPublicationService(uow),
        ExternalExecutionService(uow),
        registry,
        poll_interval_seconds=poll_interval,
        lease_seconds=lease_seconds,
        operation_timeout_seconds=operation_timeout,
        automatic_retry_limit=automatic_retry_limit,
        automatic_retry_base_delay_seconds=automatic_retry_base_delay,
        automatic_retry_max_delay_seconds=automatic_retry_max_delay,
    )
    presence = WorkerPresenceRuntime(
        WorkerPresenceService(uow),
        worker_id=resolved_worker_id,
        kind=WorkerKind.SCM,
        hostname=socket.gethostname(),
        process_id=os.getpid(),
        capabilities=tuple(registry.supported_keys),
        workspace_scope=workspace_scope,
        heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
    )
    if once:
        worked = asyncio.run(presence.run(runtime.run_once))
        typer.echo("SCM publication processed." if worked else "No SCM publication found.")
        return
    try:
        asyncio.run(presence.run(runtime.run))
    except KeyboardInterrupt:
        typer.echo("SCM publication worker stopped.")


def main() -> None:
    """Invoke the SCM publication worker application."""

    app()


if __name__ == "__main__":
    main()
