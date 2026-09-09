"""Process-level smoke test for the local Control Plane, Worker, and Jarvis stack."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx

from jb_orchestrator.application import ExternalExecutionService, SecurityService
from jb_orchestrator.config import get_settings
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.security import ApiPermission
from jb_orchestrator.system_smoke_scm import (
    GitHubApiStub,
    ScmSmokeRepository,
    prepare_scm_repository,
)
from jb_orchestrator.system_smoke_webhook import WebhookStub
from jb_orchestrator.worker import ExecutorRegistry, TaskClaim

SMOKE_EXECUTOR_KEY = "system-smoke"


class SystemSmokeError(RuntimeError):
    """A required process or cross-component contract failed."""


@dataclass(frozen=True, slots=True)
class SystemSmokeResult:
    project_id: str
    completed_execution_id: str
    cancelled_execution_id: str
    publication_id: str
    review_url: str
    service_account_id: str
    retired_credential_id: str
    replacement_credential_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": [
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
            ],
            "project_id": self.project_id,
            "executions": {
                "approved": {
                    "id": self.completed_execution_id,
                    "status": "succeeded",
                },
                "cancelled": {
                    "id": self.cancelled_execution_id,
                    "status": "cancelled",
                },
            },
            "scm_publication": {
                "id": self.publication_id,
                "provider": "github",
                "review_url": self.review_url,
                "status": "succeeded",
            },
            "credential_rotation": {
                "service_account_id": self.service_account_id,
                "retired_credential_id": self.retired_credential_id,
                "replacement_credential_id": self.replacement_credential_id,
                "authentication": "verified",
                "revocation": "verified",
                "audit": "verified",
                "status": "succeeded",
            },
            "status": "ready",
        }


@dataclass(frozen=True, slots=True)
class _SmokeServiceAccount:
    account_id: str
    credential_id: str
    token: str


@dataclass(slots=True)
class _ManagedProcess:
    name: str
    process: subprocess.Popen[bytes]
    log_path: Path
    log_handle: Any

    def tail(self) -> str:
        self.log_handle.flush()
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[-20:])

    def stop(self) -> None:
        if self.process.poll() is None:
            _terminate_process_tree(self.process)
        self.log_handle.close()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    process_group = f"-{process.pid}"
    try:
        subprocess.run(["kill", "-TERM", "--", process_group], check=False, capture_output=True)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            subprocess.run(["kill", "-KILL", "--", process_group], check=False, capture_output=True)
            process.wait(timeout=5)


def _start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    log_directory: Path,
) -> _ManagedProcess:
    log_path = log_directory / f"{name}.log"
    log_handle = log_path.open("wb")
    creationflags = (
        cast(int, getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(environment),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except OSError:
        log_handle.close()
        raise
    return _ManagedProcess(name, process, log_path, log_handle)


def _ensure_port_available(host: str, port: int) -> None:
    try:
        with socket.socket() as candidate:
            candidate.bind((host, port))
    except OSError as exc:
        raise SystemSmokeError(f"port is already in use: {host}:{port}") from exc


def _wait_for_http(
    client: httpx.Client,
    path: str,
    *,
    timeout_seconds: float,
    process: _ManagedProcess,
) -> httpx.Response:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        if process.process.poll() is not None:
            raise SystemSmokeError(f"{process.name} exited before readiness\n{process.tail()}")
        try:
            response = client.get(path)
            if response.is_success:
                return response
            last_error = f"HTTP {response.status_code}: {response.text}"
        except httpx.RequestError as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise SystemSmokeError(f"{process.name} did not become ready: {last_error}\n{process.tail()}")


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    headers: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
) -> Any:
    response = client.request(method, path, headers=headers, json=payload)
    if not response.is_success:
        raise SystemSmokeError(
            f"{method} {path} failed: HTTP {response.status_code} {response.text}"
        )
    return cast(dict[str, Any], response.json())


def _poll_execution(
    jarvis: httpx.Client,
    execution_id: str,
    expected_status: str,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unknown"
    while time.monotonic() < deadline:
        detail = _request_execution(jarvis, execution_id)
        execution = detail["execution"]
        last_status = str(execution["status"])
        if last_status == expected_status:
            return detail
        if last_status in {"succeeded", "failed", "cancelled"}:
            raise SystemSmokeError(
                f"execution {execution_id} reached {last_status}, expected {expected_status}"
            )
        time.sleep(0.2)
    raise SystemSmokeError(
        f"execution {execution_id} did not reach {expected_status}; last status: {last_status}"
    )


def _request_execution(jarvis: httpx.Client, execution_id: str) -> dict[str, Any]:
    response = jarvis.get("/api/execution", params={"executionId": execution_id})
    if not response.is_success:
        raise SystemSmokeError(
            f"GET /api/execution failed: HTTP {response.status_code} {response.text}"
        )
    return cast(dict[str, Any], response.json())


async def _issue_tokens(suffix: str) -> tuple[_SmokeServiceAccount, str]:
    settings = get_settings()
    session_factory = create_session_factory(settings)
    security = SecurityService(lambda: SqlAlchemyUnitOfWork(session_factory))
    try:
        setup = await security.issue(
            key=f"smoke-setup-{suffix}",
            name="System Smoke Setup",
            permissions=(ApiPermission.PROJECT_ADMIN,),
            all_projects=True,
        )
        jarvis = await security.issue(
            key=f"smoke-jarvis-{suffix}",
            name="System Smoke Jarvis",
            permissions=(
                ApiPermission.PROJECT_READ,
                ApiPermission.REQUEST_DISPATCH,
                ApiPermission.WORKFLOW_APPROVE,
                ApiPermission.RUN_CANCEL,
                ApiPermission.SCM_PUBLISH,
                ApiPermission.WORKSPACE_MANAGE,
                ApiPermission.NOTIFICATION_MANAGE,
            ),
            all_projects=True,
        )
        return (
            _SmokeServiceAccount(
                account_id=str(setup.account.id),
                credential_id=str(setup.credential.id),
                token=setup.token,
            ),
            jarvis.token,
        )
    finally:
        await session_factory.kw["bind"].dispose()


def _verify_credential_rotation(
    api: httpx.Client,
    identity: _SmokeServiceAccount,
) -> str:
    original_headers = {"Authorization": f"Bearer {identity.token}"}
    issued = _request(
        api,
        "POST",
        f"/v1/service-accounts/{identity.account_id}/credentials",
        headers=original_headers,
        payload={},
    )
    replacement_id = issued.get("id")
    replacement_token = issued.get("token")
    if not isinstance(replacement_id, str) or not isinstance(replacement_token, str):
        raise SystemSmokeError("credential issue response omitted replacement identity")
    if "token_digest" in issued:
        raise SystemSmokeError("credential issue response exposed a token digest")

    replacement_headers = {"Authorization": f"Bearer {replacement_token}"}
    projects = _request(api, "GET", "/v1/projects", headers=replacement_headers)
    if not isinstance(projects, list):
        raise SystemSmokeError("replacement credential did not authenticate")

    revoked = _request(
        api,
        "DELETE",
        f"/v1/service-accounts/{identity.account_id}/credentials/{identity.credential_id}",
        headers=replacement_headers,
    )
    if revoked.get("credential_id") != identity.credential_id or revoked.get("revoked") is not True:
        raise SystemSmokeError("original credential was not revoked")

    rejected = api.get("/v1/projects", headers=original_headers)
    if rejected.status_code != 401:
        raise SystemSmokeError(f"revoked credential remained usable: HTTP {rejected.status_code}")

    credentials = _request(
        api,
        "GET",
        f"/v1/service-accounts/{identity.account_id}/credentials",
        headers=replacement_headers,
    )
    if not isinstance(credentials, list):
        raise SystemSmokeError("credential inventory response is not a list")
    by_id = {item.get("id"): item for item in credentials if isinstance(item, dict)}
    if by_id.get(identity.credential_id, {}).get("active") is not False:
        raise SystemSmokeError("credential inventory did not expose original revocation")
    if by_id.get(replacement_id, {}).get("active") is not True:
        raise SystemSmokeError("credential inventory did not expose active replacement")

    events = _request(
        api,
        "GET",
        f"/v1/service-accounts/{identity.account_id}/credential-events?limit=10",
        headers=replacement_headers,
    )
    if not isinstance(events, list) or len(events) < 3:
        raise SystemSmokeError("credential audit ledger omitted rotation events")
    revoked_event, issued_event = events[:2]
    if (
        revoked_event.get("event_type") != "service_account.credential_revoked"
        or revoked_event.get("credential_id") != identity.credential_id
        or revoked_event.get("actor_credential_id") != replacement_id
    ):
        raise SystemSmokeError("credential revocation audit attribution is inconsistent")
    if (
        issued_event.get("event_type") != "service_account.credential_issued"
        or issued_event.get("credential_id") != replacement_id
        or issued_event.get("actor_credential_id") != identity.credential_id
    ):
        raise SystemSmokeError("credential issuance audit attribution is inconsistent")
    return replacement_id


async def _prepare_scm_execution(
    dispatched: Mapping[str, Any], fixture: ScmSmokeRepository, suffix: str
) -> str:
    settings = get_settings()
    session_factory = create_session_factory(settings)
    executions = ExternalExecutionService(lambda: SqlAlchemyUnitOfWork(session_factory))
    idempotency_key = f"system-smoke-scm-{suffix}"
    claim = TaskClaim(
        execution_id=UUID(str(cast(dict[str, Any], dispatched["workflow"])["id"])),
        run_id=UUID(str(cast(dict[str, Any], dispatched["run"])["id"])),
        node_key="scm-publication",
        executor_key=SMOKE_EXECUTOR_KEY,
        worker_id="system-smoke-worker",
        lease_token=uuid4(),
        idempotency_key=idempotency_key,
        visit_count=1,
        attempt_count=1,
        timeout_seconds=30,
        workflow_key="system-smoke",
        workflow_version=1,
        instructions=None,
        configuration={},
        skills=(),
    )
    try:
        execution = await executions.prepare(
            claim,
            session_key=f"system-smoke:{suffix}",
            agent_id="system-smoke",
            workspace_path=str(fixture.workspace),
            workspace_repository_path=str(fixture.workspace),
            workspace_branch=fixture.source_branch,
            workspace_base_ref=fixture.target_branch,
            workspace_scope=fixture.workspace_scope,
        )
        execution = await executions.finish(
            idempotency_key,
            ExternalExecutionStatus.SUCCEEDED,
            terminal_result={"summary": "SCM smoke worktree ready"},
        )
        return str(execution.id)
    finally:
        await session_factory.kw["bind"].dispose()


def _workflow_payload(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "version": 1,
        "entry_node": "work",
        "nodes": [
            {"key": "work", "kind": "task", "executor_key": SMOKE_EXECUTOR_KEY},
            {"key": "review", "kind": "approval"},
            {"key": "done", "kind": "terminal", "terminal_status": "succeeded"},
            {"key": "failed", "kind": "terminal", "terminal_status": "failed"},
        ],
        "edges": [
            {"source": "work", "outcome": "success", "target": "review"},
            {"source": "work", "outcome": "failure", "target": "failed"},
            {"source": "review", "outcome": "approved", "target": "done"},
            {"source": "review", "outcome": "rejected", "target": "failed"},
        ],
    }


def _run_scm_worker(
    project_root: Path,
    environment: Mapping[str, str],
    fixture: ScmSmokeRepository,
    *,
    timeout_seconds: float,
) -> None:
    worker = subprocess.run(
        [
            sys.executable,
            "-m",
            "jb_orchestrator.scm.worker_main",
            "--once",
            "--workspace-scope",
            fixture.workspace_scope,
            "--lease-seconds",
            "30",
            "--operation-timeout",
            "20",
            "--automatic-retry-limit",
            "1",
            "--automatic-retry-base-delay",
            "0.1",
            "--automatic-retry-max-delay",
            "0.1",
        ],
        cwd=project_root,
        env=dict(environment),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if worker.returncode != 0:
        output = (worker.stdout + worker.stderr).decode(errors="replace")
        raise SystemSmokeError(f"SCM worker failed with exit code {worker.returncode}\n{output}")


def _run_notification_worker(
    project_root: Path,
    environment: Mapping[str, str],
    *,
    timeout_seconds: float,
) -> None:
    worker = subprocess.run(
        [
            sys.executable,
            "-m",
            "jb_orchestrator.notifications.worker_main",
            "--once",
            "--lease-seconds",
            "20",
            "--delivery-timeout",
            "10",
            "--automatic-retry-limit",
            "1",
            "--automatic-retry-base-delay",
            "300",
            "--automatic-retry-max-delay",
            "300",
        ],
        cwd=project_root,
        env=dict(environment),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if worker.returncode != 0:
        output = (worker.stdout + worker.stderr).decode(errors="replace")
        raise SystemSmokeError(
            f"notification worker failed with exit code {worker.returncode}\n{output}"
        )


def _run_readiness_monitor(
    project_root: Path,
    environment: Mapping[str, str],
    *,
    timeout_seconds: float,
) -> None:
    monitor = subprocess.run(
        [sys.executable, "-m", "jb_orchestrator.worker_presence.monitor_main", "--once"],
        cwd=project_root,
        env=dict(environment),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if monitor.returncode != 0:
        output = (monitor.stdout + monitor.stderr).decode(errors="replace")
        raise SystemSmokeError(
            f"readiness monitor failed with exit code {monitor.returncode}\n{output}"
        )


def run_system_smoke(
    project_root: Path,
    *,
    api_port: int = 18080,
    jarvis_port: int = 13000,
    timeout_seconds: float = 60.0,
) -> SystemSmokeResult:
    """Exercise real process and HTTP boundaries against a disposable test database."""

    settings = get_settings()
    if settings.environment != "test":
        raise SystemSmokeError(
            "system smoke requires JB_ENVIRONMENT=test and a disposable database"
        )
    if not 1 <= api_port <= 65535 or not 1 <= jarvis_port <= 65535:
        raise SystemSmokeError("system smoke ports must be between 1 and 65535")
    if api_port == jarvis_port:
        raise SystemSmokeError("Control Plane and Jarvis must use different ports")
    if timeout_seconds <= 0:
        raise SystemSmokeError("system smoke timeout must be greater than zero")
    jarvis_root = project_root / "apps" / "jarvis"
    if not (jarvis_root / "node_modules").is_dir():
        raise SystemSmokeError("Jarvis dependencies are missing; run npm ci in apps/jarvis")
    node = shutil.which("node")
    if node is None:
        raise SystemSmokeError("Node.js is required for the Jarvis system smoke test")
    vinext_cli = jarvis_root / "node_modules" / "vinext" / "dist" / "cli.js"
    if not vinext_cli.is_file():
        raise SystemSmokeError("Vinext CLI is missing; run npm ci in apps/jarvis")
    if shutil.which("git") is None:
        raise SystemSmokeError("git is required for the SCM system smoke test")
    try:
        executors = ExecutorRegistry.from_entry_points().supported_keys
    except Exception as exc:
        raise SystemSmokeError(f"executor discovery failed: {exc}") from exc
    if SMOKE_EXECUTOR_KEY not in executors:
        raise SystemSmokeError(
            "system-smoke executor is not installed; run with "
            "--with-editable tools/system-smoke-executor"
        )

    host = "127.0.0.1"
    _ensure_port_available(host, api_port)
    _ensure_port_available(host, jarvis_port)
    suffix = uuid4().hex[:10]
    try:
        setup_identity, jarvis_token = asyncio.run(_issue_tokens(suffix))
    except Exception as exc:
        raise SystemSmokeError(f"cannot issue smoke service accounts: {exc}") from exc
    base_environment = os.environ.copy()
    base_environment.update(
        {
            "JB_ENVIRONMENT": "test",
            "JB_API_AUTH_ENABLED": "true",
            "JB_API_HOST": host,
            "JB_API_PORT": str(api_port),
            "JB_CONTROL_PLANE_URL": f"http://{host}:{api_port}",
        }
    )

    with tempfile.TemporaryDirectory(prefix="jb-system-smoke-") as temporary:
        log_directory = Path(temporary)
        try:
            scm_fixture = prepare_scm_repository(log_directory, suffix)
        except Exception as exc:
            raise SystemSmokeError(f"cannot prepare SCM smoke repository: {exc}") from exc
        github_stub = GitHubApiStub(
            scm_fixture.source_branch,
            scm_fixture.target_branch,
            fail_first_create=True,
        )
        github_stub.__enter__()
        webhook_secret = "system-smoke-signing-secret"
        webhook_stub = WebhookStub(webhook_secret, fail_first_delivery=True)
        webhook_stub.__enter__()
        processes: list[_ManagedProcess] = []
        clients: list[httpx.Client] = []
        try:
            api_process = _start_process(
                "control-plane",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "jb_orchestrator.api.main:app",
                    "--host",
                    host,
                    "--port",
                    str(api_port),
                ],
                cwd=project_root,
                environment=base_environment,
                log_directory=log_directory,
            )
            processes.append(api_process)
            api = httpx.Client(base_url=f"http://{host}:{api_port}", timeout=5)
            clients.append(api)
            _wait_for_http(
                api,
                "/health/ready",
                timeout_seconds=timeout_seconds,
                process=api_process,
            )

            setup_headers = {"Authorization": f"Bearer {setup_identity.token}"}
            workflow_key = f"system-smoke-{suffix}"
            project = _request(
                api,
                "POST",
                "/v1/projects",
                headers=setup_headers,
                payload={
                    "key": workflow_key,
                    "name": "System Smoke Project",
                    "repository_url": scm_fixture.repository_url,
                    "default_branch": "develop",
                },
            )
            _request(
                api,
                "POST",
                "/v1/workflows",
                headers=setup_headers,
                payload=_workflow_payload(workflow_key),
            )
            _request(
                api,
                "PUT",
                f"/v1/projects/{project['id']}/workflow-binding",
                headers=setup_headers,
                payload={"definition_key": workflow_key, "definition_version": 1},
            )
            replacement_credential_id = _verify_credential_rotation(api, setup_identity)
            jarvis_environment = base_environment | {
                "JARVIS_CONTROL_PLANE_URL": f"http://{host}:{api_port}",
                "JARVIS_API_TOKEN": jarvis_token,
            }
            jarvis_process = _start_process(
                "jarvis",
                [
                    node,
                    str(vinext_cli),
                    "dev",
                    "--port",
                    str(jarvis_port),
                    "--hostname",
                    host,
                ],
                cwd=jarvis_root,
                environment=jarvis_environment,
                log_directory=log_directory,
            )
            processes.append(jarvis_process)
            jarvis = httpx.Client(base_url=f"http://{host}:{jarvis_port}", timeout=10)
            clients.append(jarvis)
            _wait_for_http(
                jarvis,
                "/api/projects",
                timeout_seconds=timeout_seconds,
                process=jarvis_process,
            )
            notification_subscription = _request(
                jarvis,
                "POST",
                "/api/notification-subscriptions",
                payload={
                    "projectId": project["id"],
                    "providerKey": "webhook",
                    "destinationRef": "system-smoke-observer",
                    "eventTypes": ["worker.readiness_alerted"],
                },
            )
            listed_subscriptions = _request(
                jarvis,
                "GET",
                f"/api/notification-subscriptions?projectId={project['id']}",
            )
            if (
                not isinstance(listed_subscriptions, list)
                or len(listed_subscriptions) != 1
                or listed_subscriptions[0].get("id") != notification_subscription.get("id")
            ):
                raise SystemSmokeError("Jarvis did not list the notification subscription")
            configured_subscription = _request(
                jarvis,
                "PATCH",
                "/api/notification-subscriptions/configure",
                payload={
                    "projectId": project["id"],
                    "subscriptionId": notification_subscription["id"],
                    "eventTypes": [
                        "worker.readiness_alerted",
                        "worker.readiness_resolved",
                    ],
                    "enabled": True,
                },
            )
            if set(configured_subscription.get("event_types", [])) != {
                "worker.readiness_alerted",
                "worker.readiness_resolved",
            }:
                raise SystemSmokeError("Jarvis did not configure notification event filters")

            first = _request(
                jarvis,
                "POST",
                "/api/dispatch",
                headers={"Idempotency-Key": f"smoke-complete-{suffix}"},
                payload={
                    "projectId": project["id"],
                    "title": "System smoke completion",
                    "prompt": "Complete the deterministic system smoke task.",
                },
            )
            _run_readiness_monitor(
                project_root,
                base_environment,
                timeout_seconds=timeout_seconds,
            )
            unassigned = _request(
                jarvis,
                "GET",
                f"/api/worker-readiness?projectId={project['id']}",
            )
            unassigned_issues = unassigned.get("issues")
            if (
                not isinstance(unassigned_issues, list)
                or len(unassigned_issues) != 1
                or unassigned_issues[0].get("executor_key") != SMOKE_EXECUTOR_KEY
                or unassigned.get("online_execution_workers") != 0
            ):
                raise SystemSmokeError("READY task without an online worker was not diagnosed")
            unassigned_alerts = unassigned.get("alerts")
            if (
                not isinstance(unassigned_alerts, list)
                or len(unassigned_alerts) != 1
                or unassigned_alerts[0].get("status") != "active"
            ):
                raise SystemSmokeError("readiness monitor did not persist the assignment alert")
            alerted_deliveries = _request(
                jarvis,
                "GET",
                f"/api/notification-deliveries?projectId={project['id']}",
            )
            if (
                not isinstance(alerted_deliveries, list)
                or len(alerted_deliveries) != 1
                or alerted_deliveries[0].get("subscription_id")
                != notification_subscription.get("id")
                or alerted_deliveries[0].get("event_type") != "worker.readiness_alerted"
                or alerted_deliveries[0].get("status") != "pending"
            ):
                raise SystemSmokeError("readiness alert did not create a delivery intent")
            worker = subprocess.run(
                [sys.executable, "-m", "jb_orchestrator.worker.main", "--once"],
                cwd=project_root,
                env=base_environment,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            if worker.returncode != 0:
                output = (worker.stdout + worker.stderr).decode(errors="replace")
                raise SystemSmokeError(
                    f"worker failed with exit code {worker.returncode}\n{output}"
                )

            first_id = str(first["workflow"]["id"])
            awaiting = _poll_execution(
                jarvis, first_id, "awaiting_approval", timeout_seconds=timeout_seconds
            )
            assigned = _request(
                jarvis,
                "GET",
                f"/api/worker-readiness?projectId={project['id']}",
            )
            if assigned.get("issues") != []:
                raise SystemSmokeError("completed task remained in worker readiness diagnostics")
            _run_readiness_monitor(
                project_root,
                base_environment,
                timeout_seconds=timeout_seconds,
            )
            resolved = _request(
                jarvis,
                "GET",
                f"/api/worker-readiness?projectId={project['id']}",
            )
            resolved_alerts = resolved.get("alerts")
            if (
                not isinstance(resolved_alerts, list)
                or len(resolved_alerts) != 1
                or resolved_alerts[0].get("status") != "resolved"
            ):
                raise SystemSmokeError("readiness monitor did not resolve the assignment alert")
            resolved_deliveries = _request(
                jarvis,
                "GET",
                f"/api/notification-deliveries?projectId={project['id']}",
            )
            if not isinstance(resolved_deliveries, list) or {
                delivery.get("event_type") for delivery in resolved_deliveries
            } != {
                "worker.readiness_alerted",
                "worker.readiness_resolved",
            }:
                raise SystemSmokeError("readiness resolution did not create a delivery intent")
            webhook_environment = base_environment | {
                "JB_WEBHOOK_DESTINATIONS": json.dumps(
                    {
                        "system-smoke-observer": {
                            "url": webhook_stub.endpoint_url,
                            "signing_secret": webhook_secret,
                        }
                    }
                ),
                "JB_WEBHOOK_ALLOW_INSECURE_LOOPBACK": "true",
            }
            _run_notification_worker(
                project_root,
                webhook_environment,
                timeout_seconds=timeout_seconds,
            )
            _run_notification_worker(
                project_root,
                webhook_environment,
                timeout_seconds=timeout_seconds,
            )
            delivered = _request(
                jarvis,
                "GET",
                f"/api/notification-deliveries?projectId={project['id']}",
            )
            if not isinstance(delivered, list) or {item.get("status") for item in delivered} != {
                "failed",
                "succeeded",
            }:
                raise SystemSmokeError("Webhook failure was not durably classified")
            failed_delivery = next(item for item in delivered if item.get("status") == "failed")
            if failed_delivery.get("failure_code") != "provider_unavailable":
                raise SystemSmokeError("transient Webhook failure was not classified")
            if (
                failed_delivery.get("failure_retryable") is not True
                or failed_delivery.get("automatic_retry_limit") != 1
                or not failed_delivery.get("next_attempt_at")
            ):
                raise SystemSmokeError("Webhook automatic retry was not durably scheduled")
            cancelled_notification_retry = _request(
                jarvis,
                "POST",
                "/api/notification-deliveries/automatic-retry/cancel",
                payload={
                    "projectId": project["id"],
                    "deliveryId": failed_delivery["id"],
                },
            )
            if (
                cancelled_notification_retry.get("status") != "failed"
                or cancelled_notification_retry.get("next_attempt_at") is not None
            ):
                raise SystemSmokeError("Jarvis did not cancel notification automatic retry")
            retried_delivery = _request(
                jarvis,
                "POST",
                "/api/notification-deliveries/retry",
                payload={
                    "projectId": project["id"],
                    "deliveryId": failed_delivery["id"],
                },
            )
            if retried_delivery.get("status") != "pending":
                raise SystemSmokeError("failed Webhook delivery was not queued for retry")
            _run_notification_worker(
                project_root,
                webhook_environment,
                timeout_seconds=timeout_seconds,
            )
            completed_deliveries = _request(
                jarvis,
                "GET",
                f"/api/notification-deliveries?projectId={project['id']}",
            )
            if (
                not isinstance(completed_deliveries, list)
                or {item.get("status") for item in completed_deliveries} != {"succeeded"}
                or any("lease_token" in item for item in completed_deliveries)
            ):
                raise SystemSmokeError("retried Webhook delivery did not succeed")
            attempts = _request(
                jarvis,
                "GET",
                "/api/notification-deliveries/attempts"
                f"?projectId={project['id']}&deliveryId={failed_delivery['id']}",
            )
            if (
                not isinstance(attempts, list)
                or len(attempts) != 2
                or attempts[0].get("trigger") != "manual"
                or attempts[0].get("status") != "succeeded"
                or attempts[1].get("trigger") != "initial"
                or attempts[1].get("failure_code") != "provider_unavailable"
                or any("lease_token" in attempt for attempt in attempts)
            ):
                raise SystemSmokeError("Webhook delivery attempt ledger is incomplete")
            if {item.get("event_type") for item in webhook_stub.deliveries} != {
                "worker.readiness_alerted",
                "worker.readiness_resolved",
            }:
                raise SystemSmokeError("signed Webhook endpoint did not receive both events")
            if webhook_stub.delivery_attempts != 3:
                raise SystemSmokeError("Webhook manual retry did not execute exactly once")
            if not awaiting["artifacts"]:
                raise SystemSmokeError("worker completed without producing a task artifact")
            _request(
                jarvis,
                "POST",
                "/api/approval",
                payload={"executionId": first_id, "nodeKey": "review", "approved": True},
            )
            _poll_execution(jarvis, first_id, "succeeded", timeout_seconds=timeout_seconds)

            try:
                external_execution_id = asyncio.run(
                    _prepare_scm_execution(first, scm_fixture, suffix)
                )
            except Exception as exc:
                raise SystemSmokeError(f"cannot prepare SCM execution: {exc}") from exc
            publication = _request(
                jarvis,
                "POST",
                "/api/scm-publications",
                payload={
                    "externalExecutionId": external_execution_id,
                    "providerKey": "github",
                    "targetBranch": scm_fixture.target_branch,
                    "title": "System smoke publication",
                    "body": "Created by the disposable SCM system smoke.",
                    "idempotencyKey": f"smoke-publication-{suffix}",
                },
            )
            scm_environment = base_environment | {
                "JB_GITHUB_TOKEN": "system-smoke-token",
                "JB_GITHUB_WORKSPACE_ROOTS": json.dumps([str(log_directory.resolve())]),
                "JB_GITHUB_API_URL": github_stub.api_url,
                "JB_GITHUB_WEB_HOST": "github.local",
                "JB_GITHUB_ALLOW_INSECURE_LOOPBACK": "true",
            }
            _run_scm_worker(
                project_root,
                scm_environment,
                scm_fixture,
                timeout_seconds=timeout_seconds,
            )
            publications = _request(
                jarvis,
                "GET",
                f"/api/scm-publications?externalExecutionId={external_execution_id}",
            )
            if not isinstance(publications, list) or len(publications) != 1:
                raise SystemSmokeError("SCM publication was not durably listed")
            failed_publication = cast(dict[str, Any], publications[0])
            if failed_publication.get("status") != "failed":
                raise SystemSmokeError("first SCM publication attempt did not fail as expected")
            if failed_publication.get("failure_code") != "provider_unavailable":
                raise SystemSmokeError("transient SCM provider failure was not classified")
            if failed_publication.get("failure_retryable") is not True:
                raise SystemSmokeError("transient SCM provider failure was not marked retryable")
            if failed_publication.get("automatic_retry_limit") != 1:
                raise SystemSmokeError("SCM automatic retry limit was not persisted")
            if not failed_publication.get("next_attempt_at"):
                raise SystemSmokeError("SCM automatic retry was not durably scheduled")
            cancelled_retry = _request(
                jarvis,
                "POST",
                "/api/scm-publications/automatic-retry/cancel",
                payload={"publicationId": publication["id"]},
            )
            if (
                cancelled_retry.get("status") != "failed"
                or cancelled_retry.get("next_attempt_at") is not None
            ):
                raise SystemSmokeError("SCM automatic retry schedule was not cancelled")
            immediate_retry = _request(
                jarvis,
                "POST",
                "/api/scm-publications/retry",
                payload={"publicationId": publication["id"]},
            )
            if immediate_retry.get("status") != "pending":
                raise SystemSmokeError("SCM publication was not queued for immediate retry")
            _run_scm_worker(
                project_root,
                scm_environment,
                scm_fixture,
                timeout_seconds=timeout_seconds,
            )
            publications = _request(
                jarvis,
                "GET",
                f"/api/scm-publications?externalExecutionId={external_execution_id}",
            )
            completed_publication = cast(dict[str, Any], publications[0])
            if completed_publication.get("status") != "succeeded":
                raise SystemSmokeError(
                    "SCM publication did not succeed: "
                    f"{completed_publication.get('failure_reason', 'unknown failure')}"
                )
            result = completed_publication.get("result")
            if not isinstance(result, dict) or not github_stub.created:
                raise SystemSmokeError("GitHub pull request was not created by the SCM worker")
            review_url = str(result.get("review_url", ""))
            if review_url != "https://github.local/system-smoke/repository/pull/53":
                raise SystemSmokeError("SCM publication returned an unexpected review URL")
            if completed_publication.get("attempt_count") != 2:
                raise SystemSmokeError("SCM publication retry attempt was not counted")
            attempts = _request(
                jarvis,
                "GET",
                f"/api/scm-publications/attempts?publicationId={publication['id']}",
            )
            if not isinstance(attempts, list) or len(attempts) != 2:
                raise SystemSmokeError("SCM publication attempt ledger was not durably listed")
            latest_attempt, initial_attempt = attempts
            if (
                latest_attempt.get("attempt_number") != 2
                or latest_attempt.get("trigger") != "manual"
                or latest_attempt.get("status") != "succeeded"
            ):
                raise SystemSmokeError("manual SCM recovery attempt was not recorded")
            if (
                initial_attempt.get("attempt_number") != 1
                or initial_attempt.get("trigger") != "initial"
                or initial_attempt.get("status") != "failed"
                or initial_attempt.get("failure_code") != "provider_unavailable"
            ):
                raise SystemSmokeError("initial SCM provider failure was not recorded")
            if "lease_token" in latest_attempt or "lease_token" in initial_attempt:
                raise SystemSmokeError("SCM attempt API exposed an internal lease token")
            worker_instances = _request(jarvis, "GET", "/api/workers")
            if not isinstance(worker_instances, list):
                raise SystemSmokeError("Worker presence ledger was not listed through Jarvis")
            worker_kinds = {
                str(instance.get("kind"))
                for instance in worker_instances
                if instance.get("observed_status") == "stopped"
            }
            if not {
                "execution",
                "scm",
                "readiness_monitor",
                "notification",
            }.issubset(worker_kinds):
                raise SystemSmokeError("required Worker process lifetimes were not recorded")

            second = _request(
                jarvis,
                "POST",
                "/api/dispatch",
                headers={"Idempotency-Key": f"smoke-cancel-{suffix}"},
                payload={
                    "projectId": project["id"],
                    "title": "System smoke cancellation",
                    "prompt": "Cancel this deterministic system smoke task.",
                },
            )
            second_id = str(second["workflow"]["id"])
            _request(
                jarvis,
                "POST",
                "/api/cancellation",
                payload={
                    "executionId": second_id,
                    "confirmation": f"취소 {second_id[:8]}",
                },
            )
            _poll_execution(jarvis, second_id, "cancelled", timeout_seconds=timeout_seconds)
            return SystemSmokeResult(
                str(project["id"]),
                first_id,
                second_id,
                str(publication["id"]),
                review_url,
                setup_identity.account_id,
                setup_identity.credential_id,
                replacement_credential_id,
            )
        except SystemSmokeError:
            raise
        except Exception as exc:
            raise SystemSmokeError(f"unexpected system smoke failure: {exc}") from exc
        finally:
            for client in clients:
                client.close()
            for process in reversed(processes):
                process.stop()
            github_stub.__exit__(None, None, None)
            webhook_stub.__exit__(None, None, None)
