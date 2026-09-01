from typer.testing import CliRunner

from jb_orchestrator.worker.main import app

runner = CliRunner()


def test_worker_once() -> None:
    result = runner.invoke(app, ["--once"])

    assert result.exit_code == 0
    assert "mode=once" in result.stdout
