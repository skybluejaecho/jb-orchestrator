import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from jb_orchestrator.release_check import (
    ReleaseCheckError,
    release_check_steps,
    run_release_check,
)


def prepare_project(root: Path) -> None:
    for relative in (
        "pyproject.toml",
        "uv.lock",
        "apps/jarvis/package.json",
        "tools/openclaw-gateway-spike/package.json",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


def test_standard_gate_covers_every_offline_release_surface(tmp_path: Path) -> None:
    prepare_project(tmp_path)

    steps = release_check_steps(tmp_path, include_system_smoke=False)

    assert [step.name for step in steps] == [
        "python-lock",
        "python-lint",
        "python-format",
        "python-types",
        "python-tests",
        "jarvis-format",
        "jarvis-lint",
        "jarvis-tests",
        "jarvis-build",
        "openclaw-contract",
    ]
    assert steps[5].working_directory == tmp_path / "apps" / "jarvis"
    assert steps[-1].working_directory == tmp_path / "tools" / "openclaw-gateway-spike"


def test_full_gate_appends_migration_and_process_smoke(tmp_path: Path) -> None:
    prepare_project(tmp_path)

    steps = release_check_steps(tmp_path, include_system_smoke=True)

    assert [step.name for step in steps[-2:]] == ["database-migrations", "system-smoke"]
    assert "tools/system-smoke-executor" in steps[-1].command


def test_release_check_runs_in_order_and_reports_success(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    prepare_project(tmp_path)
    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_run(command: list[str], **options: Any) -> SimpleNamespace:
        calls.append((tuple(command), options["cwd"]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("shutil.which", lambda executable: f"/bin/{executable}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_release_check(tmp_path, timeout_seconds=12)

    assert result.as_dict()["status"] == "ready"
    assert result.system_smoke_included is False
    assert [command[0] for command, _ in calls] == ["/bin/uv"] * 5 + ["/bin/npm"] * 5


def test_release_check_stops_at_first_failure(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    prepare_project(tmp_path)

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        returncode = 2 if command[1:3] == ["run", "mypy"] else 0
        return SimpleNamespace(returncode=returncode, stdout="type error\n", stderr="")

    monkeypatch.setattr("shutil.which", lambda executable: f"/bin/{executable}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ReleaseCheckError, match=r"(?s)python-types failed.*type error"):
        run_release_check(tmp_path)


def test_full_gate_fails_closed_outside_test_environment(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    prepare_project(tmp_path)
    monkeypatch.delenv("JB_ENVIRONMENT", raising=False)

    with pytest.raises(ReleaseCheckError, match="JB_ENVIRONMENT=test"):
        run_release_check(tmp_path, include_system_smoke=True)


def test_release_check_reports_missing_executable(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    prepare_project(tmp_path)
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(ReleaseCheckError, match="uv is not installed"):
        run_release_check(tmp_path)


def test_release_check_reports_timeout(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    prepare_project(tmp_path)

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("shutil.which", lambda executable: f"/bin/{executable}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ReleaseCheckError, match="exceeded the 1 second timeout"):
        run_release_check(tmp_path, timeout_seconds=1)
