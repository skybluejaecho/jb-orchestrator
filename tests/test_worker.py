import pytest
from typer.testing import CliRunner

from jb_orchestrator.worker.main import app
from jb_orchestrator.worker.models import TaskClaim, TaskResult
from jb_orchestrator.worker.registry import ExecutorRegistry
from jb_orchestrator.worker.runtime import WorkerRuntime
from jb_orchestrator.workflows import NodeOutcome

runner = CliRunner()


class CliExecutor:
    async def execute(self, claim: TaskClaim) -> TaskResult:
        return TaskResult(outcome=NodeOutcome.SUCCESS)


def test_worker_lists_installed_executors() -> None:
    result = runner.invoke(app, ["--list-executors"])

    assert result.exit_code == 0
    assert "No executor adapters installed" in result.stdout


def test_worker_refuses_to_claim_without_an_executor() -> None:
    result = runner.invoke(app, ["--once"])

    assert result.exit_code == 2
    assert "No executor adapters installed" in result.output


def test_worker_once_uses_discovered_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ExecutorRegistry({"fake": CliExecutor()})

    def discover(cls: type[ExecutorRegistry]) -> ExecutorRegistry:
        return registry

    async def run_once(runtime: WorkerRuntime) -> bool:
        return False

    monkeypatch.setattr(ExecutorRegistry, "from_entry_points", classmethod(discover))
    monkeypatch.setattr(WorkerRuntime, "run_once", run_once)

    result = runner.invoke(app, ["--once", "--worker-id", "test-worker"])

    assert result.exit_code == 0
    assert "No supported READY task found" in result.stdout
