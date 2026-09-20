from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from jb_orchestrator.config import Settings
from jb_orchestrator.preflight import (
    PreflightCheck,
    PreflightError,
    PreflightReport,
    PreflightRole,
    run_preflight,
)


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "api_auth_enabled": True,
        "database_url": "postgresql+asyncpg://user:secret@database/jb",
        "api_token": "client-token",
        "control_plane_url": "https://control.example.com",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def statuses(report: PreflightReport) -> dict[str, str]:
    return {check.key: check.status.value for check in report.checks}


async def database_ready(*_: object) -> list[PreflightCheck]:
    return []


@pytest.mark.asyncio
async def test_unknown_role_is_rejected() -> None:
    with pytest.raises(PreflightError, match="unknown role"):
        await run_preflight(roles=["scheduler"], settings=production_settings())


@pytest.mark.asyncio
async def test_production_control_plane_requires_authentication(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("jb_orchestrator.preflight._inspect_database", database_ready)

    report = await run_preflight(
        roles=[PreflightRole.CONTROL_PLANE],
        settings=production_settings(api_auth_enabled=False),
        environment={},
    )

    assert report.ready is False
    assert statuses(report)["control-plane.authentication"] == "fail"
    assert report.as_dict()["summary"]["fail"] == 1


@pytest.mark.asyncio
async def test_non_production_environment_is_a_warning_not_a_failure() -> None:
    report = await run_preflight(
        roles=[PreflightRole.MCP],
        settings=production_settings(environment="staging"),
        environment={},
    )

    assert report.ready is True
    assert statuses(report)["deployment.environment"] == "warning"


@pytest.mark.asyncio
async def test_mcp_requires_token_and_secure_remote_control_plane() -> None:
    report = await run_preflight(
        roles=[PreflightRole.MCP],
        settings=production_settings(
            api_token=None, control_plane_url="http://control.example.com"
        ),
        environment={},
    )

    assert report.ready is False
    assert statuses(report) == {
        "deployment.environment": "pass",
        "mcp.control-plane-url": "fail",
        "mcp.api-token": "fail",
    }


@pytest.mark.asyncio
async def test_jarvis_reports_configuration_without_exposing_secrets() -> None:
    report = await run_preflight(
        roles=[PreflightRole.JARVIS],
        settings=production_settings(),
        environment={
            "JARVIS_CONTROL_PLANE_URL": "https://control.example.com",
            "JARVIS_API_TOKEN": "never-render-this-token",
        },
    )

    assert report.ready is True
    assert "never-render-this-token" not in str(report.as_dict())


@pytest.mark.asyncio
async def test_task_worker_validates_openclaw_runtime_contract(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "jb_orchestrator.preflight.ExecutorRegistry.from_entry_points",
        lambda: SimpleNamespace(supported_keys=frozenset({"openclaw"})),
    )
    monkeypatch.setattr("jb_orchestrator.preflight.shutil.which", lambda _: "node")
    monkeypatch.setattr(
        "jb_orchestrator.preflight.subprocess.run",
        lambda *_args, **_options: SimpleNamespace(returncode=0, stdout="v22.19.0\n"),
    )
    monkeypatch.setattr("jb_orchestrator.preflight._inspect_database", database_ready)

    report = await run_preflight(
        roles=[PreflightRole.TASK_WORKER],
        project_root=tmp_path,
        settings=production_settings(),
        environment={
            "JB_OPENCLAW_BRIDGE_PATH": str(bridge),
            "OPENCLAW_GATEWAY_URL": "wss://gateway.example.com",
            "OPENCLAW_GATEWAY_TLS_FINGERPRINT": "sha256:fingerprint",
            "OPENCLAW_GATEWAY_TOKEN": "never-render-this-token",
        },
    )

    assert report.ready is True
    assert statuses(report)["openclaw.credentials"] == "pass"
    assert "never-render-this-token" not in str(report.as_dict())


@pytest.mark.asyncio
async def test_task_worker_rejects_unsupported_openclaw_node_version(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "jb_orchestrator.preflight.ExecutorRegistry.from_entry_points",
        lambda: SimpleNamespace(supported_keys=frozenset({"openclaw"})),
    )
    monkeypatch.setattr("jb_orchestrator.preflight.shutil.which", lambda _: "node")
    monkeypatch.setattr(
        "jb_orchestrator.preflight.subprocess.run",
        lambda *_args, **_options: SimpleNamespace(returncode=0, stdout="v22.18.0\n"),
    )
    monkeypatch.setattr("jb_orchestrator.preflight._inspect_database", database_ready)

    report = await run_preflight(
        roles=[PreflightRole.TASK_WORKER],
        project_root=tmp_path,
        settings=production_settings(),
        environment={
            "JB_OPENCLAW_BRIDGE_PATH": str(bridge),
            "OPENCLAW_GATEWAY_TOKEN": "token",
        },
    )

    assert report.ready is False
    assert statuses(report)["openclaw.node"] == "fail"


@pytest.mark.asyncio
async def test_provider_configuration_failure_is_safely_reported(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_discovery() -> object:
        raise ValueError("secret provider detail")

    monkeypatch.setattr(
        "jb_orchestrator.preflight.NotificationProviderRegistry.from_entry_points",
        fail_discovery,
    )
    monkeypatch.setattr("jb_orchestrator.preflight._inspect_database", database_ready)

    report = await run_preflight(
        roles=[PreflightRole.NOTIFICATION_WORKER],
        settings=production_settings(),
        environment={},
    )

    assert report.ready is False
    assert "secret provider detail" not in str(report.as_dict())
    assert "ValueError" in str(report.as_dict())


@pytest.mark.asyncio
async def test_duplicate_roles_are_reported_once() -> None:
    report = await run_preflight(
        roles=[PreflightRole.MCP, "mcp"],
        settings=production_settings(),
        environment={},
    )

    assert report.roles == (PreflightRole.MCP,)
