import pytest
from typer.testing import CliRunner

from jb_orchestrator.scm import ScmPublisherRegistry
from jb_orchestrator.scm.runtime import ScmPublicationRuntime
from jb_orchestrator.scm.worker_main import app
from tests.scm.test_runtime import RecordingPublisher

runner = CliRunner()


def test_worker_lists_installed_publishers() -> None:
    result = runner.invoke(app, ["--list-publishers"])

    assert result.exit_code == 0
    assert "No SCM publisher adapters installed" in result.stdout


def test_worker_refuses_to_run_without_a_publisher() -> None:
    result = runner.invoke(app, ["--once", "--workspace-scope", "scope-a"])

    assert result.exit_code == 2
    assert "No SCM publisher adapters installed" in result.output


def test_worker_requires_workspace_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ScmPublisherRegistry({"github": RecordingPublisher()})

    def discover(cls: type[ScmPublisherRegistry]) -> ScmPublisherRegistry:
        return registry

    monkeypatch.setattr(ScmPublisherRegistry, "from_entry_points", classmethod(discover))

    result = runner.invoke(app, ["--once"])

    assert result.exit_code == 2
    assert "--workspace-scope is required" in result.output


def test_worker_once_uses_discovered_publishers(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ScmPublisherRegistry({"github": RecordingPublisher()})

    def discover(cls: type[ScmPublisherRegistry]) -> ScmPublisherRegistry:
        return registry

    async def run_once(runtime: ScmPublicationRuntime) -> bool:
        return False

    monkeypatch.setattr(ScmPublisherRegistry, "from_entry_points", classmethod(discover))
    monkeypatch.setattr(ScmPublicationRuntime, "run_once", run_once)

    result = runner.invoke(
        app,
        ["--once", "--workspace-scope", "scope-a", "--worker-id", "test-worker"],
    )

    assert result.exit_code == 0
    assert "No SCM publication found" in result.stdout
