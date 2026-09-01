import json
from typing import Any

import httpx
from pytest import MonkeyPatch
from typer.testing import CliRunner

from jb_orchestrator.cli.main import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_doctor_command() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["service"] == "jb-orchestrator"
    assert payload["database_configured"] is True


def test_project_register_calls_control_plane(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request(
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        timeout: float,
    ) -> httpx.Response:
        captured.update(method=method, url=url, payload=json, timeout=timeout)
        request = httpx.Request(method, url)
        return httpx.Response(
            201,
            request=request,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "key": "jb-orchestrator",
            },
        )

    monkeypatch.setattr(httpx, "request", fake_request)

    result = runner.invoke(
        app,
        [
            "project",
            "register",
            "--key",
            "jb-orchestrator",
            "--name",
            "JB Orchestrator",
            "--repository-url",
            "https://github.com/example/jb-orchestrator.git",
            "--default-branch",
            "develop",
        ],
    )

    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:8000/v1/projects"
    assert captured["payload"]["default_branch"] == "develop"
