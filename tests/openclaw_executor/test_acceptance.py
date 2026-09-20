import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from jb_openclaw_executor.acceptance import (
    OpenClawAcceptanceError,
    app,
    local_diagnostics,
    run_acceptance,
)
from jb_openclaw_executor.workspace import OpenClawWorkspaceError
from typer.testing import CliRunner

runner = CliRunner()


class FakeBridge:
    def __init__(self, *, replay_mismatch: bool = False, status: str = "completed") -> None:
        self.replay_mismatch = replay_mismatch
        self.status = status
        self.starts: list[dict[str, Any]] = []
        self.cancelled: list[str] = []

    async def inspect(self) -> dict[str, Any]:
        return {"health": {"status": "ok"}, "agents": [], "sessions": []}

    async def start(self, request: dict[str, Any]) -> dict[str, Any]:
        self.starts.append(request)
        key = str(request["idempotencyKey"])
        if key.endswith(":first"):
            suffix = "-mismatch" if self.replay_mismatch and len(self.starts) == 2 else ""
            return {"runId": f"run-first{suffix}"}
        if key.endswith(":continuation"):
            return {"runId": "run-continuation"}
        return {"runId": "run-cancel"}

    async def wait(self, run_id: str, timeout_ms: int) -> dict[str, Any]:
        return {"runId": run_id, "status": self.status, "timeoutMs": timeout_ms}

    async def cancel(self, run_id: str) -> dict[str, Any]:
        self.cancelled.append(run_id)
        return {"runId": run_id, "status": "cancelled"}


async def test_live_acceptance_checks_idempotency_continuation_and_cancellation() -> None:
    bridge = FakeBridge()

    report = await run_acceptance(
        bridge,
        session_key="agent:reviewer:acceptance",
        idempotency_prefix="acceptance-42",
        message="Inspect this repository",
        continuation_message="Confirm continuation",
        timeout_seconds=30,
        verify_cancellation=True,
    )

    assert report.idempotent_run_id == "run-first"
    assert report.continuation_run_id == "run-continuation"
    assert report.cancelled_run_id == "run-cancel"
    assert [value["idempotencyKey"] for value in bridge.starts] == [
        "acceptance-42:first",
        "acceptance-42:first",
        "acceptance-42:continuation",
        "acceptance-42:cancel",
    ]
    assert {value["sessionKey"] for value in bridge.starts} == {"agent:reviewer:acceptance"}
    assert bridge.cancelled == ["run-cancel"]


async def test_live_acceptance_fails_when_idempotent_start_changes_run() -> None:
    with pytest.raises(OpenClawAcceptanceError, match="different run IDs"):
        await run_acceptance(
            FakeBridge(replay_mismatch=True),
            session_key="agent:reviewer:acceptance",
            idempotency_prefix="acceptance-42",
            message="Inspect",
            continuation_message="Continue",
            timeout_seconds=30,
            verify_cancellation=False,
        )


async def test_live_acceptance_fails_on_non_successful_terminal_status() -> None:
    with pytest.raises(OpenClawAcceptanceError, match="ended with status: failed"):
        await run_acceptance(
            FakeBridge(status="failed"),
            session_key="agent:reviewer:acceptance",
            idempotency_prefix="acceptance-42",
            message="Inspect",
            continuation_message="Continue",
            timeout_seconds=30,
            verify_cancellation=False,
        )


def test_local_diagnostics_accepts_stored_device_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("// bridge", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "device-tokens.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "v22.19.0\n", ""),
    )

    result = local_diagnostics(
        bridge,
        node_executable="node",
        environment={"JB_OPENCLAW_DEVICE_STATE_DIR": str(state)},
    )

    assert result["credential_source"] == "device_token"
    assert result["node_version"] == "v22.19.0"


def test_local_diagnostics_requires_remote_tls_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("// bridge", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "v22.19.0\n", ""),
    )

    with pytest.raises(OpenClawAcceptanceError, match="TLS_FINGERPRINT"):
        local_diagnostics(
            bridge,
            node_executable="node",
            environment={
                "OPENCLAW_GATEWAY_URL": "wss://gateway.example.com",
                "OPENCLAW_GATEWAY_TOKEN": "secret",
            },
        )


def test_workspace_cleanup_requires_exact_execution_confirmation() -> None:
    execution_id = uuid4()

    result = runner.invoke(
        app,
        [
            "workspace",
            "cleanup",
            "--external-execution-id",
            str(execution_id),
            "--merged-into",
            "develop",
            "--confirm",
            "different-id",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, OpenClawWorkspaceError)
