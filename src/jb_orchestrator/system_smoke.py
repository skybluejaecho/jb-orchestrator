"""Process-level smoke test for the local Control Plane, Worker, and Jarvis stack."""

import asyncio
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
from uuid import uuid4

import httpx

from jb_orchestrator.application import SecurityService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.security import ApiPermission
from jb_orchestrator.worker import ExecutorRegistry

SMOKE_EXECUTOR_KEY = "system-smoke"


class SystemSmokeError(RuntimeError):
    """A required process or cross-component contract failed."""


@dataclass(frozen=True, slots=True)
class SystemSmokeResult:
    project_id: str
    completed_execution_id: str
    cancelled_execution_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": ["postgresql", "control-plane", "worker", "jarvis"],
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
            "status": "ready",
        }


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
        return
    process_group = f"-{process.pid}"
    try:
        subprocess.run(["kill", "-TERM", process_group], check=False, capture_output=True)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            subprocess.run(["kill", "-KILL", process_group], check=False, capture_output=True)
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
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
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


async def _issue_tokens(suffix: str) -> tuple[str, str]:
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
            ),
            all_projects=True,
        )
        return setup.token, jarvis.token
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


def run_system_smoke(
    project_root: Path,
    *,
    api_port: int = 18080,
    jarvis_port: int = 13000,
    timeout_seconds: float = 30.0,
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
    npm = shutil.which("npm")
    if npm is None:
        raise SystemSmokeError("npm is required for the Jarvis system smoke test")
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
        setup_token, jarvis_token = asyncio.run(_issue_tokens(suffix))
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

            setup_headers = {"Authorization": f"Bearer {setup_token}"}
            workflow_key = f"system-smoke-{suffix}"
            project = _request(
                api,
                "POST",
                "/v1/projects",
                headers=setup_headers,
                payload={
                    "key": workflow_key,
                    "name": "System Smoke Project",
                    "repository_url": "https://example.invalid/system-smoke.git",
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

            jarvis_environment = base_environment | {
                "JARVIS_CONTROL_PLANE_URL": f"http://{host}:{api_port}",
                "JARVIS_API_TOKEN": jarvis_token,
            }
            jarvis_process = _start_process(
                "jarvis",
                [npm, "run", "dev", "--", "--port", str(jarvis_port), "--hostname", host],
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
            if not awaiting["artifacts"]:
                raise SystemSmokeError("worker completed without producing a task artifact")
            _request(
                jarvis,
                "POST",
                "/api/approval",
                payload={"executionId": first_id, "nodeKey": "review", "approved": True},
            )
            _poll_execution(jarvis, first_id, "succeeded", timeout_seconds=timeout_seconds)

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
            return SystemSmokeResult(str(project["id"]), first_id, second_id)
        except SystemSmokeError:
            raise
        except Exception as exc:
            raise SystemSmokeError(f"unexpected system smoke failure: {exc}") from exc
        finally:
            for client in clients:
                client.close()
            for process in reversed(processes):
                process.stop()
