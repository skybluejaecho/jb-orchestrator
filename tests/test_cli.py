import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from pytest import MonkeyPatch
from typer.testing import CliRunner

from jb_orchestrator.cli.main import app
from jb_orchestrator.config import get_settings
from jb_orchestrator.preflight import (
    PreflightCheck,
    PreflightReport,
    PreflightRole,
    PreflightStatus,
)
from jb_orchestrator.release_check import ReleaseCheckResult
from jb_orchestrator.system_smoke import SystemSmokeResult

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


def test_bundle_validate_command_does_not_require_control_plane(tmp_path: Path) -> None:
    bundle = tmp_path / "orchestrator.yaml"
    bundle.write_text("schema_version: 1\n", encoding="utf-8")

    result = runner.invoke(app, ["bundle", "validate", str(bundle)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"external_dependencies": [], "status": "valid"}


def test_bundle_init_command_creates_starter_without_overwriting(tmp_path: Path) -> None:
    destination = tmp_path / "starter"

    created = runner.invoke(app, ["bundle", "init", str(destination)])
    repeated = runner.invoke(app, ["bundle", "init", str(destination)])

    assert created.exit_code == 0
    assert json.loads(created.stdout)["status"] == "created"
    assert (destination / "orchestrator.yaml").is_file()
    assert repeated.exit_code == 1
    assert "already exists" in repeated.stderr


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


def test_credential_commands_use_control_plane_api(monkeypatch: MonkeyPatch) -> None:
    account_id = "00000000-0000-0000-0000-000000000001"
    credential_id = "00000000-0000-0000-0000-000000000002"
    requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        del headers, timeout
        requests.append((method, url, json))
        request = httpx.Request(method, url)
        if method == "POST":
            payload: Any = {
                "id": credential_id,
                "account_id": account_id,
                "token": "jbsa_token",
            }
            status_code = 201
        elif method == "GET" and "/credential-events" not in url:
            payload = [{"id": credential_id, "account_id": account_id}]
            status_code = 200
        elif method == "GET":
            payload = [{"sequence": 3, "event_type": "service_account.credential_revoked"}]
            status_code = 200
        else:
            payload = {
                "account_id": account_id,
                "credential_id": credential_id,
                "revoked": True,
            }
            status_code = 200
        return httpx.Response(status_code, request=request, json=payload)

    monkeypatch.setattr(httpx, "request", fake_request)

    issued = runner.invoke(
        app,
        [
            "auth",
            "credential",
            "issue",
            account_id,
            "--expires-at",
            "2030-01-01T00:00:00+00:00",
        ],
    )
    listed = runner.invoke(app, ["auth", "credential", "list", account_id])
    audited = runner.invoke(
        app,
        ["auth", "credential", "audit", account_id, "--before-sequence", "4", "--limit", "20"],
    )
    revoked = runner.invoke(
        app,
        ["auth", "credential", "revoke", account_id, credential_id],
    )

    assert issued.exit_code == listed.exit_code == audited.exit_code == revoked.exit_code == 0
    base_url = f"http://127.0.0.1:8000/v1/service-accounts/{account_id}/credentials"
    assert requests == [
        ("POST", base_url, {"expires_at": "2030-01-01T00:00:00+00:00"}),
        ("GET", base_url, None),
        (
            "GET",
            f"http://127.0.0.1:8000/v1/service-accounts/{account_id}/"
            "credential-events?before_sequence=4&limit=20",
            None,
        ),
        ("DELETE", f"{base_url}/{credential_id}", None),
    ]


def test_service_account_inventory_commands_use_control_plane_api(
    monkeypatch: MonkeyPatch,
) -> None:
    account_id = "00000000-0000-0000-0000-000000000001"
    requests: list[tuple[str, str]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        del json, headers, timeout
        requests.append((method, url))
        request = httpx.Request(method, url)
        payload: Any = {"id": account_id} if url.endswith(account_id) else [{"id": account_id}]
        return httpx.Response(200, request=request, json=payload)

    monkeypatch.setattr(httpx, "request", fake_request)

    listed = runner.invoke(
        app,
        [
            "auth",
            "account",
            "list",
            "--disabled",
            "--key-prefix",
            "client",
            "--after-key",
            "client-alpha",
            "--limit",
            "25",
        ],
    )
    shown = runner.invoke(app, ["auth", "account", "show", account_id])
    diagnosed = runner.invoke(
        app,
        [
            "auth",
            "doctor",
            "--issues-only",
            "--key-prefix",
            "client",
            "--after-key",
            "client-alpha",
            "--limit",
            "25",
            "--warning-seconds",
            "86400",
        ],
    )

    assert listed.exit_code == shown.exit_code == diagnosed.exit_code == 0
    assert requests == [
        (
            "GET",
            "http://127.0.0.1:8000/v1/service-accounts?"
            "enabled=False&key_prefix=client&after_key=client-alpha&limit=25",
        ),
        ("GET", f"http://127.0.0.1:8000/v1/service-accounts/{account_id}"),
        (
            "GET",
            "http://127.0.0.1:8000/v1/service-accounts/readiness?"
            "issues_only=True&key_prefix=client&after_key=client-alpha&limit=25&"
            "warning_seconds=86400",
        ),
    ]


def test_mcp_config_uses_placeholder_instead_of_configured_secret(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    monkeypatch.setenv("JB_API_TOKEN", "must-not-be-rendered")
    get_settings.cache_clear()
    try:
        result = runner.invoke(app, ["mcp", "config", "--project-path", str(tmp_path)])
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    assert "must-not-be-rendered" not in result.stdout
    payload = json.loads(result.stdout)
    config = payload["mcpServers"]["jb-orchestrator"]
    assert config["args"] == ["run", "--project", str(tmp_path.resolve()), "jb-mcp"]
    assert config["env"]["JB_API_TOKEN"] == "<service-account-token>"


def test_mcp_check_reports_authorized_project(monkeypatch: MonkeyPatch) -> None:
    project_id = "00000000-0000-0000-0000-000000000001"

    async def fake_get_project(requested_id: object) -> dict[str, str]:
        assert str(requested_id) == project_id
        return {"id": project_id, "key": "alpha"}

    monkeypatch.setattr("jb_orchestrator.cli.main.get_mcp_project", fake_get_project)

    result = runner.invoke(app, ["mcp", "check", "--project-id", project_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["authenticated"] is True
    assert payload["project"]["key"] == "alpha"


def test_mcp_smoke_reports_stdio_runtime_inventory(monkeypatch: MonkeyPatch) -> None:
    project_id = "00000000-0000-0000-0000-000000000001"

    async def fake_probe(_: object) -> SimpleNamespace:
        return SimpleNamespace(
            server_name="jb-orchestrator",
            server_version="1.0",
            tools=("dispatch_request", "get_project"),
            project={"id": project_id, "key": "alpha"},
        )

    monkeypatch.setattr("jb_orchestrator.cli.main.probe_mcp_runtime", fake_probe)

    result = runner.invoke(app, ["mcp", "smoke", "--project-id", project_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["server"]["name"] == "jb-orchestrator"
    assert payload["tools"] == ["dispatch_request", "get_project"]


def test_system_smoke_reports_process_boundary_result(monkeypatch: MonkeyPatch) -> None:
    project_id = "00000000-0000-0000-0000-000000000001"
    captured: dict[str, object] = {}

    def fake_smoke(*_: object, **options: object) -> SystemSmokeResult:
        captured.update(options)
        return SystemSmokeResult(
            project_id=project_id,
            completed_execution_id="00000000-0000-0000-0000-000000000002",
            cancelled_execution_id="00000000-0000-0000-0000-000000000003",
            publication_id="00000000-0000-0000-0000-000000000004",
            review_url="https://github.local/system-smoke/repository/pull/53",
            service_account_id="00000000-0000-0000-0000-000000000005",
            retired_credential_id="00000000-0000-0000-0000-000000000006",
            replacement_credential_id="00000000-0000-0000-0000-000000000007",
        )

    monkeypatch.setattr("jb_orchestrator.cli.main.run_system_smoke", fake_smoke)

    result = runner.invoke(app, ["system", "smoke"])

    assert result.exit_code == 0
    assert captured["timeout_seconds"] == 60.0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["components"] == [
        "postgresql",
        "control-plane",
        "worker",
        "worker-presence",
        "worker-readiness",
        "scm-worker",
        "github-publisher",
        "notification-worker",
        "webhook-notifier",
        "jarvis",
    ]
    assert payload["executions"]["approved"]["status"] == "succeeded"
    assert payload["executions"]["cancelled"]["status"] == "cancelled"
    assert payload["scm_publication"]["status"] == "succeeded"
    assert payload["scm_publication"]["provider"] == "github"
    assert payload["credential_rotation"] == {
        "service_account_id": "00000000-0000-0000-0000-000000000005",
        "retired_credential_id": "00000000-0000-0000-0000-000000000006",
        "replacement_credential_id": "00000000-0000-0000-0000-000000000007",
        "authentication": "verified",
        "revocation": "verified",
        "audit": "verified",
        "status": "succeeded",
    }


def test_release_check_command_reports_gate_result(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_release_check(*_: object, **options: object) -> ReleaseCheckResult:
        captured.update(options)
        return ReleaseCheckResult(
            checks=("python-lock", "python-tests"),
            duration_seconds=1.25,
            system_smoke_included=False,
        )

    monkeypatch.setattr("jb_orchestrator.cli.main.run_release_check", fake_release_check)

    result = runner.invoke(app, ["system", "release-check", "--timeout-seconds", "30"])

    assert result.exit_code == 0
    assert captured == {"include_system_smoke": False, "timeout_seconds": 30.0}
    assert json.loads(result.stdout) == {
        "checks": ["python-lock", "python-tests"],
        "duration_seconds": 1.25,
        "status": "ready",
        "system_smoke_included": False,
    }


def test_preflight_command_passes_repeated_roles_and_reports_success(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_preflight(**options: object) -> PreflightReport:
        captured.update(options)
        return PreflightReport(
            environment="production",
            roles=(PreflightRole.MCP, PreflightRole.JARVIS),
            checks=(
                PreflightCheck(
                    key="mcp.api-token",
                    status=PreflightStatus.PASS,
                    detail="API token is configured",
                    roles=(PreflightRole.MCP,),
                ),
            ),
        )

    monkeypatch.setattr("jb_orchestrator.cli.main.run_preflight", fake_preflight)

    result = runner.invoke(
        app,
        ["system", "preflight", "--role", "mcp", "--role", "jarvis"],
    )

    assert result.exit_code == 0
    assert captured["roles"] == ["mcp", "jarvis"]
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["summary"] == {"fail": 0, "pass": 1, "warning": 0}


def test_preflight_command_returns_nonzero_with_structured_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    async def fake_preflight(**_: object) -> PreflightReport:
        return PreflightReport(
            environment="production",
            roles=(PreflightRole.CONTROL_PLANE,),
            checks=(
                PreflightCheck(
                    key="control-plane.authentication",
                    status=PreflightStatus.FAIL,
                    detail="API authentication is required",
                    roles=(PreflightRole.CONTROL_PLANE,),
                ),
            ),
        )

    monkeypatch.setattr("jb_orchestrator.cli.main.run_preflight", fake_preflight)

    result = runner.invoke(app, ["system", "preflight", "--role", "control-plane"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ready"] is False
