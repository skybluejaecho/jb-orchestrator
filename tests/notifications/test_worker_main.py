from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from typer.testing import CliRunner

from jb_orchestrator.notifications import NotificationProviderRegistry
from jb_orchestrator.notifications.runtime import NotificationRuntime
from jb_orchestrator.notifications.worker_main import app
from jb_orchestrator.worker_presence.runtime import WorkerPresenceRuntime
from tests.notifications.test_runtime import Provider

runner = CliRunner()


def test_worker_lists_installed_providers() -> None:
    result = runner.invoke(app, ["--list-providers"])
    assert result.exit_code == 0
    assert "No notification providers installed" in result.stdout


def test_worker_refuses_to_run_without_provider() -> None:
    result = runner.invoke(app, ["--once"])
    assert result.exit_code == 2
    assert "No notification providers installed" in result.output


def test_worker_once_uses_discovered_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = NotificationProviderRegistry({"fixture": Provider()})

    def discover(cls: type[NotificationProviderRegistry]) -> NotificationProviderRegistry:
        return registry

    async def run_once(runtime: NotificationRuntime) -> bool:
        return False

    async def run_with_presence(
        runtime: WorkerPresenceRuntime,
        operation: Callable[[], Coroutine[Any, Any, bool]],
    ) -> bool:
        return await operation()

    monkeypatch.setattr(NotificationProviderRegistry, "from_entry_points", classmethod(discover))
    monkeypatch.setattr(NotificationRuntime, "run_once", run_once)
    monkeypatch.setattr(WorkerPresenceRuntime, "run", run_with_presence)

    result = runner.invoke(app, ["--once", "--worker-id", "test-notification-worker"])
    assert result.exit_code == 0
    assert "No notification delivery found" in result.stdout
