from pathlib import Path

import pytest

from jb_orchestrator.config import get_settings
from jb_orchestrator.system_smoke import (
    SystemSmokeError,
    _workflow_payload,
    run_system_smoke,
)


def test_system_smoke_fails_closed_outside_test_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JB_ENVIRONMENT", "local")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemSmokeError, match="JB_ENVIRONMENT=test"):
            run_system_smoke(tmp_path)
    finally:
        get_settings.cache_clear()


def test_smoke_workflow_exercises_worker_and_approval_paths() -> None:
    payload = _workflow_payload("system-smoke-test")

    assert payload["entry_node"] == "work"
    assert payload["nodes"][0]["executor_key"] == "system-smoke"
    assert {edge["outcome"] for edge in payload["edges"]} == {
        "success",
        "failure",
        "approved",
        "rejected",
    }
