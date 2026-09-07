"""Notification delivery worker process entry point."""

import asyncio
import os
import socket

import typer

from jb_orchestrator.application import NotificationService, WorkerPresenceService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.notifications.registry import (
    NotificationProviderRegistrationError,
    NotificationProviderRegistry,
)
from jb_orchestrator.notifications.runtime import NotificationRuntime
from jb_orchestrator.worker_presence import WorkerKind
from jb_orchestrator.worker_presence.runtime import WorkerPresenceRuntime

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def run(
    *,
    once: bool = typer.Option(False, help="Poll once and exit."),
    list_providers: bool = typer.Option(False, help="List installed providers and exit."),
    worker_id: str | None = typer.Option(None, help="Stable notification worker identity."),
    poll_interval: float = typer.Option(1.0, min=0.1),
    lease_seconds: int = typer.Option(60, min=2),
    delivery_timeout: float = typer.Option(30.0, min=0.1),
) -> None:
    """Start a worker using installed notification provider entry points."""

    try:
        registry = NotificationProviderRegistry.from_entry_points()
    except NotificationProviderRegistrationError as exc:
        typer.echo(f"Notification provider discovery failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if list_providers:
        keys = sorted(registry.supported_keys)
        typer.echo("\n".join(keys) if keys else "No notification providers installed.")
        return
    if not registry.supported_keys:
        typer.echo(
            "No notification providers installed in the "
            "jb_orchestrator.notification_providers entry-point group.",
            err=True,
        )
        raise typer.Exit(code=2)

    settings = get_settings()
    session_factory = create_session_factory(settings)
    uow = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    resolved_worker_id = worker_id or f"{socket.gethostname()}-notification-{os.getpid()}"
    runtime = NotificationRuntime(
        resolved_worker_id,
        NotificationService(uow),
        registry,
        poll_interval_seconds=poll_interval,
        lease_seconds=lease_seconds,
        delivery_timeout_seconds=delivery_timeout,
    )
    presence = WorkerPresenceRuntime(
        WorkerPresenceService(uow),
        worker_id=resolved_worker_id,
        kind=WorkerKind.NOTIFICATION,
        hostname=socket.gethostname(),
        process_id=os.getpid(),
        capabilities=tuple(registry.supported_keys),
        heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
    )
    if once:
        worked = asyncio.run(presence.run(runtime.run_once))
        typer.echo("Notification delivered." if worked else "No notification delivery found.")
        return
    try:
        asyncio.run(presence.run(runtime.run))
    except KeyboardInterrupt:
        typer.echo("Notification worker stopped.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
