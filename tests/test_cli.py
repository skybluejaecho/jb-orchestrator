import json
from pathlib import Path
from typing import Any

import httpx
from pytest import MonkeyPatch
from typer.testing import CliRunner

from jb_orchestrator.cli.main import app
from jb_orchestrator.config import get_settings

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


def test_skill_digest_command(tmp_path: Path) -> None:
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")

    result = runner.invoke(app, ["skill", "digest", str(skill)])

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("sha256:")
    assert len(result.stdout.strip()) == 71


def test_skill_digest_rejects_a_file(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# Review\n", encoding="utf-8")

    result = runner.invoke(app, ["skill", "digest", str(skill_file)])

    assert result.exit_code == 1
    assert "cannot digest skill" in result.stderr


def test_project_register_calls_control_plane(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request(
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        captured.update(method=method, url=url, payload=json, headers=headers, timeout=timeout)
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


def test_control_plane_call_includes_configured_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JB_API_TOKEN", "secret-token")
    get_settings.cache_clear()
    captured: dict[str, Any] = {}

    def fake_request(
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        captured["headers"] = headers
        return httpx.Response(200, request=httpx.Request(method, url), json={})

    monkeypatch.setattr(httpx, "request", fake_request)
    try:
        result = runner.invoke(app, ["request", "get", "00000000-0000-0000-0000-000000000001"])
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}
