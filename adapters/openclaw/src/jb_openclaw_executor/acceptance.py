"""Explicit live acceptance commands for the optional OpenClaw adapter."""

import asyncio
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

import typer

from jb_openclaw_executor.bridge import (
    OpenClawBridge,
    OpenClawBridgeClient,
    OpenClawBridgeError,
)
from jb_openclaw_executor.executor import SUCCESS_STATUSES
from jb_openclaw_executor.factory import OpenClawExecutorSettings
from jb_openclaw_executor.workspace import (
    OpenClawWorkspaceError,
    OpenClawWorkspaceManager,
    WorkspaceReview,
)
from jb_orchestrator.application.exceptions import ApplicationError
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.config import get_settings
from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition
from jb_orchestrator.external_executions import ExternalExecution
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory

app = typer.Typer(no_args_is_help=True, help="Diagnose and accept a live OpenClaw Gateway.")
workspace_app = typer.Typer(no_args_is_help=True, help="Review and release managed worktrees.")
app.add_typer(workspace_app, name="workspace")


class OpenClawAcceptanceError(RuntimeError):
    """A live Gateway failed one required acceptance invariant."""


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    gateway: dict[str, Any]
    session_key: str
    idempotent_run_id: str
    first_terminal_status: str
    continuation_run_id: str
    continuation_terminal_status: str
    cancelled_run_id: str | None = None


def bridge_from_settings() -> OpenClawBridgeClient:
    settings = OpenClawExecutorSettings()
    return OpenClawBridgeClient(
        settings.bridge_path,
        node_executable=settings.node_executable,
    )


def external_execution_service() -> ExternalExecutionService:
    session_factory = create_session_factory(get_settings())
    return ExternalExecutionService(lambda: SqlAlchemyUnitOfWork(session_factory))


def workspace_manager_from_settings() -> OpenClawWorkspaceManager:
    settings = OpenClawExecutorSettings()
    return OpenClawWorkspaceManager(
        workspace_root=settings.workspace_root,
        repository_roots=settings.repository_roots,
        git_executable=settings.git_executable,
    )


async def load_workspace_review(
    service: ExternalExecutionService,
    manager: OpenClawWorkspaceManager,
    execution_id: UUID,
    *,
    merged_into: str,
) -> tuple[ExternalExecution, WorkspaceReview | None]:
    execution = await service.get_by_id(execution_id)
    if execution.workspace_released_at is not None:
        return execution, None
    return execution, await manager.review(execution, merged_into=merged_into)


async def release_managed_workspace(
    service: ExternalExecutionService,
    manager: OpenClawWorkspaceManager,
    execution_id: UUID,
    *,
    merged_into: str,
) -> tuple[ExternalExecution, WorkspaceReview | None]:
    execution = await service.get_by_id(execution_id)
    if execution.workspace_released_at is not None:
        return execution, None
    review = await manager.cleanup(execution, merged_into=merged_into)
    return await service.release_workspace(execution.id), review


def local_diagnostics(
    bridge_path: Path, *, node_executable: str, environment: dict[str, str]
) -> dict[str, Any]:
    resolved_bridge = bridge_path.resolve()
    if not resolved_bridge.is_file():
        raise OpenClawAcceptanceError(f"OpenClaw bridge not found: {resolved_bridge}")
    try:
        result = subprocess.run(
            [node_executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OpenClawAcceptanceError("Node.js executable is unavailable") from exc
    node_version = result.stdout.strip()
    version_match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", node_version)
    if version_match is None or tuple(map(int, version_match.groups())) < (22, 19, 0):
        raise OpenClawAcceptanceError("Node.js 22.19.0 or newer is required")
    gateway_url = environment.get("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789").strip()
    parsed_url = urlsplit(gateway_url)
    if parsed_url.scheme not in {"ws", "wss"} or not parsed_url.hostname:
        raise OpenClawAcceptanceError("OPENCLAW_GATEWAY_URL must use ws:// or wss://")
    if parsed_url.username or parsed_url.password:
        raise OpenClawAcceptanceError("Gateway credentials must not be embedded in its URL")
    remote_tls = parsed_url.scheme == "wss" and parsed_url.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }
    if remote_tls and not environment.get("OPENCLAW_GATEWAY_TLS_FINGERPRINT", "").strip():
        raise OpenClawAcceptanceError(
            "remote wss Gateway requires OPENCLAW_GATEWAY_TLS_FINGERPRINT"
        )
    has_bootstrap = bool(
        environment.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
        or environment.get("OPENCLAW_GATEWAY_PASSWORD", "").strip()
    )
    state_dir = Path(
        environment.get("JB_OPENCLAW_DEVICE_STATE_DIR", ".jb-orchestrator/openclaw-device")
    ).resolve()
    has_device_state = (state_dir / "device-tokens.json").is_file()
    if not has_bootstrap and not has_device_state:
        raise OpenClawAcceptanceError(
            "a bootstrap credential or stored OpenClaw device token is required"
        )
    return {
        "bridge_path": str(resolved_bridge),
        "node_version": node_version,
        "gateway_url": gateway_url,
        "credential_source": "bootstrap" if has_bootstrap else "device_token",
        "device_state_dir": str(state_dir),
        "tls_fingerprint_configured": bool(
            environment.get("OPENCLAW_GATEWAY_TLS_FINGERPRINT", "").strip()
        ),
    }


async def run_acceptance(
    bridge: OpenClawBridge,
    *,
    session_key: str,
    idempotency_prefix: str,
    message: str,
    continuation_message: str,
    timeout_seconds: int,
    verify_cancellation: bool,
) -> AcceptanceReport:
    session_key = _required_value(session_key, "session key")
    idempotency_prefix = _required_value(idempotency_prefix, "idempotency prefix")
    message = _required_value(message, "message")
    continuation_message = _required_value(continuation_message, "continuation message")
    gateway = _gateway_summary(await bridge.inspect())
    first_request = {
        "message": message,
        "sessionKey": session_key,
        "idempotencyKey": f"{idempotency_prefix}:first",
        "timeoutSeconds": timeout_seconds,
    }
    first = await bridge.start(first_request)
    first_run_id = _run_id(first)
    replay = await bridge.start(first_request)
    if _run_id(replay) != first_run_id:
        raise OpenClawAcceptanceError("Gateway returned different run IDs for one idempotency key")
    first_terminal = await bridge.wait(first_run_id, timeout_seconds * 1_000)
    first_status = _successful_status(first_terminal, "first")

    continuation = await bridge.start(
        {
            "message": continuation_message,
            "sessionKey": session_key,
            "idempotencyKey": f"{idempotency_prefix}:continuation",
            "timeoutSeconds": timeout_seconds,
        }
    )
    continuation_run_id = _run_id(continuation)
    continuation_terminal = await bridge.wait(continuation_run_id, timeout_seconds * 1_000)
    continuation_status = _successful_status(continuation_terminal, "continuation")

    cancelled_run_id = None
    if verify_cancellation:
        cancellable = await bridge.start(
            {
                "message": "This is an acceptance cancellation probe. Wait for cancellation.",
                "sessionKey": session_key,
                "idempotencyKey": f"{idempotency_prefix}:cancel",
                "timeoutSeconds": timeout_seconds,
            }
        )
        cancelled_run_id = _run_id(cancellable)
        await bridge.cancel(cancelled_run_id)

    return AcceptanceReport(
        gateway=gateway,
        session_key=session_key,
        idempotent_run_id=first_run_id,
        first_terminal_status=first_status,
        continuation_run_id=continuation_run_id,
        continuation_terminal_status=continuation_status,
        cancelled_run_id=cancelled_run_id,
    )


def _run_id(response: dict[str, Any]) -> str:
    run_id = response.get("runId")
    if not isinstance(run_id, str) or not run_id:
        raise OpenClawAcceptanceError("OpenClaw response did not include a runId")
    return run_id


def _required_value(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise OpenClawAcceptanceError(f"{label} must not be empty")
    return normalized


def _successful_status(terminal: dict[str, Any], stage: str) -> str:
    status = str(terminal.get("status", "unknown")).lower()
    if status not in SUCCESS_STATUSES:
        raise OpenClawAcceptanceError(f"{stage} acceptance run ended with status: {status}")
    return status


def _gateway_summary(value: dict[str, Any]) -> dict[str, Any]:
    health = value.get("health")
    health_status = health.get("status") if isinstance(health, dict) else None
    return {
        "health_status": health_status,
        "agent_count": _collection_count(value.get("agents"), "agents"),
        "session_count": _collection_count(value.get("sessions"), "sessions"),
    }


def _collection_count(value: Any, key: str) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        items = value.get(key, value.get("items"))
        return len(items) if isinstance(items, list) else None
    return None


@app.command()
def doctor() -> None:
    """Validate local prerequisites and inspect the configured live Gateway."""

    settings = OpenClawExecutorSettings()
    diagnostics = local_diagnostics(
        settings.bridge_path,
        node_executable=settings.node_executable,
        environment=dict(os.environ),
    )
    diagnostics["gateway"] = _gateway_summary(asyncio.run(bridge_from_settings().inspect()))
    typer.echo(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))


@app.command()
def acceptance(
    session_key: Annotated[str, typer.Option(help="Dedicated acceptance session key.")],
    idempotency_prefix: Annotated[
        str, typer.Option(help="Stable unique prefix for this acceptance attempt.")
    ],
    message: Annotated[str, typer.Option(help="First harmless live probe request.")],
    continuation_message: Annotated[
        str, typer.Option(help="Second request proving same-session continuation.")
    ] = "Confirm that this is the continuation of the acceptance session.",
    timeout_seconds: Annotated[
        int, typer.Option(min=1, max=1800, help="Per-run timeout in seconds.")
    ] = 120,
    verify_cancellation: Annotated[
        bool, typer.Option(help="Start and immediately abort an additional live probe.")
    ] = False,
) -> None:
    """Run explicit live idempotency, continuation, and optional cancellation checks."""

    settings = OpenClawExecutorSettings()
    local_diagnostics(
        settings.bridge_path,
        node_executable=settings.node_executable,
        environment=dict(os.environ),
    )
    report = asyncio.run(
        run_acceptance(
            OpenClawBridgeClient(
                settings.bridge_path,
                node_executable=settings.node_executable,
            ),
            session_key=session_key,
            idempotency_prefix=idempotency_prefix,
            message=message,
            continuation_message=continuation_message,
            timeout_seconds=timeout_seconds,
            verify_cancellation=verify_cancellation,
        )
    )
    typer.echo(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))


@workspace_app.command("inspect")
def inspect_workspace(
    external_execution_id: Annotated[UUID, typer.Option(help="External execution UUID.")],
    merged_into: Annotated[
        str, typer.Option(help="Local target ref used only for merge-readiness checks.")
    ],
) -> None:
    """Inspect cleanliness and whether a managed branch is merged into a local ref."""

    execution, review = asyncio.run(
        load_workspace_review(
            external_execution_service(),
            workspace_manager_from_settings(),
            external_execution_id,
            merged_into=merged_into,
        )
    )
    if execution.workspace_released_at is not None:
        typer.echo(
            json.dumps(
                {
                    "external_execution_id": str(execution.id),
                    "released_at": execution.workspace_released_at.isoformat(),
                    "status": "released",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    if review is None:
        raise RuntimeError("active workspace review did not return a result")
    payload = asdict(review)
    payload["external_execution_id"] = str(execution.id)
    payload["status"] = "reviewed"
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


@workspace_app.command("cleanup")
def cleanup_workspace(
    external_execution_id: Annotated[UUID, typer.Option(help="External execution UUID.")],
    merged_into: Annotated[
        str, typer.Option(help="Local ref that must already contain the workspace HEAD.")
    ],
    confirm: Annotated[
        str, typer.Option(help="Repeat the exact external execution UUID to authorize removal.")
    ],
) -> None:
    """Remove one clean, terminal, already-merged worktree and its exact local branch."""

    if confirm.strip() != str(external_execution_id):
        raise OpenClawWorkspaceError("cleanup confirmation must equal the external execution UUID")
    released, review = asyncio.run(
        release_managed_workspace(
            external_execution_service(),
            workspace_manager_from_settings(),
            external_execution_id,
            merged_into=merged_into,
        )
    )
    if review is None:
        typer.echo(
            json.dumps(
                {
                    "external_execution_id": str(released.id),
                    "released_at": released.workspace_released_at.isoformat()
                    if released.workspace_released_at is not None
                    else None,
                    "status": "already_released",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    payload = asdict(review)
    payload.update(
        {
            "external_execution_id": str(released.id),
            "released_at": released.workspace_released_at.isoformat()
            if released.workspace_released_at is not None
            else None,
            "status": "released",
        }
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    try:
        app()
    except (
        ApplicationError,
        DomainValidationError,
        InvalidStateTransition,
        OpenClawAcceptanceError,
        OpenClawBridgeError,
        OpenClawWorkspaceError,
    ) as exc:
        typer.echo(f"OpenClaw validation failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
