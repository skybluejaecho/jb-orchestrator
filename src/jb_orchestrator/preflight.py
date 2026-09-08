"""Role-scoped deployment preflight checks."""

import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from jb_orchestrator.config import Settings, get_settings
from jb_orchestrator.notifications import NotificationProviderRegistry
from jb_orchestrator.scm import ScmPublisherRegistry
from jb_orchestrator.worker import ExecutorRegistry


class PreflightError(ValueError):
    """The requested preflight scope is invalid."""


class PreflightRole(StrEnum):
    CONTROL_PLANE = "control-plane"
    TASK_WORKER = "task-worker"
    SCM_WORKER = "scm-worker"
    NOTIFICATION_WORKER = "notification-worker"
    READINESS_MONITOR = "readiness-monitor"
    MCP = "mcp"
    JARVIS = "jarvis"


class PreflightStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


ALL_PREFLIGHT_ROLES = tuple(PreflightRole)
DATABASE_ROLES = frozenset(
    {
        PreflightRole.CONTROL_PLANE,
        PreflightRole.TASK_WORKER,
        PreflightRole.SCM_WORKER,
        PreflightRole.NOTIFICATION_WORKER,
        PreflightRole.READINESS_MONITOR,
    }
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    key: str
    status: PreflightStatus
    detail: str
    roles: tuple[PreflightRole, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "key": self.key,
            "roles": [role.value for role in self.roles],
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class PreflightReport:
    environment: str
    roles: tuple[PreflightRole, ...]
    checks: tuple[PreflightCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.status is not PreflightStatus.FAIL for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        counts = {
            status.value: sum(check.status is status for check in self.checks)
            for status in PreflightStatus
        }
        return {
            "checks": [check.as_dict() for check in self.checks],
            "environment": self.environment,
            "ready": self.ready,
            "roles": [role.value for role in self.roles],
            "summary": counts,
        }


async def run_preflight(
    *,
    roles: Iterable[str | PreflightRole] = ALL_PREFLIGHT_ROLES,
    project_root: Path | None = None,
    settings: Settings | None = None,
    environment: Mapping[str, str] | None = None,
) -> PreflightReport:
    """Inspect the selected deployment roles without exposing credential values."""

    resolved_roles = _resolve_roles(roles)
    resolved_settings = settings or get_settings()
    resolved_environment = environment if environment is not None else os.environ
    root = (project_root or Path.cwd()).resolve()
    checks = _static_checks(resolved_settings, resolved_environment, resolved_roles, root)
    if DATABASE_ROLES.intersection(resolved_roles):
        checks.extend(await _inspect_database(resolved_settings, root, resolved_roles))
    return PreflightReport(
        environment=resolved_settings.environment,
        roles=resolved_roles,
        checks=tuple(checks),
    )


def _resolve_roles(roles: Iterable[str | PreflightRole]) -> tuple[PreflightRole, ...]:
    requested = tuple(roles)
    if not requested:
        return ALL_PREFLIGHT_ROLES
    resolved: set[PreflightRole] = set()
    for role in requested:
        try:
            resolved.add(role if isinstance(role, PreflightRole) else PreflightRole(role))
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ALL_PREFLIGHT_ROLES)
            raise PreflightError(f"unknown role {role!r}; allowed roles: {allowed}") from exc
    return tuple(role for role in ALL_PREFLIGHT_ROLES if role in resolved)


def _static_checks(
    settings: Settings,
    environment: Mapping[str, str],
    roles: tuple[PreflightRole, ...],
    project_root: Path,
) -> list[PreflightCheck]:
    checks = [
        _check(
            "deployment.environment",
            PreflightStatus.PASS
            if settings.environment == "production"
            else PreflightStatus.WARNING,
            "production environment selected"
            if settings.environment == "production"
            else f"running preflight for {settings.environment}, not production",
            roles,
        )
    ]
    if DATABASE_ROLES.intersection(roles):
        database_scheme = urlsplit(settings.database_url).scheme.split("+")[0]
        checks.append(
            _check(
                "database.backend",
                PreflightStatus.PASS
                if database_scheme in {"postgres", "postgresql"}
                else PreflightStatus.FAIL,
                "PostgreSQL backend configured"
                if database_scheme in {"postgres", "postgresql"}
                else "PostgreSQL is required as the orchestration source of truth",
                tuple(role for role in roles if role in DATABASE_ROLES),
            )
        )
    if PreflightRole.CONTROL_PLANE in roles:
        checks.extend(_control_plane_checks(settings))
    if PreflightRole.TASK_WORKER in roles:
        checks.extend(_task_worker_checks(environment, project_root))
    if PreflightRole.SCM_WORKER in roles:
        checks.append(_registry_check(PreflightRole.SCM_WORKER, "scm.publishers"))
    if PreflightRole.NOTIFICATION_WORKER in roles:
        checks.append(_registry_check(PreflightRole.NOTIFICATION_WORKER, "notification.providers"))
    if PreflightRole.MCP in roles:
        checks.extend(
            _control_plane_client_checks(
                settings.control_plane_url,
                settings.api_token is not None,
                role=PreflightRole.MCP,
                environment_name=settings.environment,
            )
        )
    if PreflightRole.JARVIS in roles:
        checks.extend(
            _control_plane_client_checks(
                environment.get("JARVIS_CONTROL_PLANE_URL", ""),
                bool(environment.get("JARVIS_API_TOKEN", "").strip()),
                role=PreflightRole.JARVIS,
                environment_name=settings.environment,
            )
        )
    return checks


def _control_plane_checks(settings: Settings) -> list[PreflightCheck]:
    role = (PreflightRole.CONTROL_PLANE,)
    auth_required = settings.environment == "production" or settings.api_host not in LOOPBACK_HOSTS
    return [
        _check(
            "control-plane.authentication",
            PreflightStatus.PASS
            if settings.api_auth_enabled or not auth_required
            else PreflightStatus.FAIL,
            "API authentication enabled"
            if settings.api_auth_enabled
            else (
                "API authentication is required for production or non-loopback binding"
                if auth_required
                else "loopback development binding does not require API authentication"
            ),
            role,
        ),
        _check(
            "control-plane.binding",
            PreflightStatus.PASS,
            "loopback binding configured"
            if settings.api_host in LOOPBACK_HOSTS
            else "non-loopback binding configured",
            role,
        ),
    ]


def _task_worker_checks(environment: Mapping[str, str], project_root: Path) -> list[PreflightCheck]:
    adapter_check = _registry_check(PreflightRole.TASK_WORKER, "task-worker.executors")
    checks = [adapter_check]
    if adapter_check.status is PreflightStatus.PASS and "openclaw" in adapter_check.detail:
        checks.extend(_openclaw_checks(environment, project_root))
    return checks


def _registry_check(role: PreflightRole, key: str) -> PreflightCheck:
    try:
        if role is PreflightRole.TASK_WORKER:
            supported = ExecutorRegistry.from_entry_points().supported_keys
        elif role is PreflightRole.SCM_WORKER:
            supported = ScmPublisherRegistry.from_entry_points().supported_keys
        else:
            supported = NotificationProviderRegistry.from_entry_points().supported_keys
    except Exception as exc:
        return _check(
            key,
            PreflightStatus.FAIL,
            f"adapter discovery or configuration failed ({type(exc).__name__})",
            (role,),
        )
    if not supported:
        return _check(key, PreflightStatus.FAIL, "no installed adapters found", (role,))
    return _check(key, PreflightStatus.PASS, f"installed: {', '.join(sorted(supported))}", (role,))


def _openclaw_checks(environment: Mapping[str, str], project_root: Path) -> list[PreflightCheck]:
    role = (PreflightRole.TASK_WORKER,)
    bridge = Path(
        environment.get("JB_OPENCLAW_BRIDGE_PATH", "tools/openclaw-gateway-spike/src/bridge.mjs")
    )
    if not bridge.is_absolute():
        bridge = project_root / bridge
    node = environment.get("JB_OPENCLAW_NODE_EXECUTABLE", "node").strip()
    gateway = environment.get("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789").strip()
    parsed_gateway = urlsplit(gateway)
    gateway_valid = parsed_gateway.scheme in {"ws", "wss"} and bool(parsed_gateway.hostname)
    remote_gateway = parsed_gateway.hostname not in LOOPBACK_HOSTS
    has_credential = bool(
        environment.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
        or environment.get("OPENCLAW_GATEWAY_PASSWORD", "").strip()
    )
    device_state = Path(
        environment.get("JB_OPENCLAW_DEVICE_STATE_DIR", ".jb-orchestrator/openclaw-device")
    )
    if not device_state.is_absolute():
        device_state = project_root / device_state
    has_device_token = (device_state / "device-tokens.json").is_file()
    return [
        _check(
            "openclaw.bridge",
            PreflightStatus.PASS if bridge.is_file() else PreflightStatus.FAIL,
            "bridge file is available" if bridge.is_file() else "OpenClaw bridge file is missing",
            role,
        ),
        _node_check(node),
        _check(
            "openclaw.gateway",
            PreflightStatus.PASS
            if gateway_valid and (not remote_gateway or parsed_gateway.scheme == "wss")
            else PreflightStatus.FAIL,
            "Gateway URL uses an accepted transport"
            if gateway_valid and (not remote_gateway or parsed_gateway.scheme == "wss")
            else "Gateway URL must use ws for loopback or wss for a remote host",
            role,
        ),
        _check(
            "openclaw.tls-pinning",
            PreflightStatus.PASS
            if not remote_gateway
            or bool(environment.get("OPENCLAW_GATEWAY_TLS_FINGERPRINT", "").strip())
            else PreflightStatus.FAIL,
            "TLS pinning is configured or the Gateway is loopback-only"
            if not remote_gateway
            or bool(environment.get("OPENCLAW_GATEWAY_TLS_FINGERPRINT", "").strip())
            else "remote Gateway requires a TLS certificate fingerprint",
            role,
        ),
        _check(
            "openclaw.credentials",
            PreflightStatus.PASS if has_credential or has_device_token else PreflightStatus.FAIL,
            "bootstrap credential or stored device token is available"
            if has_credential or has_device_token
            else "bootstrap credential or stored device token is required",
            role,
        ),
    ]


def _node_check(node_executable: str) -> PreflightCheck:
    role = (PreflightRole.TASK_WORKER,)
    executable = shutil.which(node_executable) if node_executable else None
    if executable is None:
        return _check(
            "openclaw.node",
            PreflightStatus.FAIL,
            "Node.js executable is unavailable",
            role,
        )
    try:
        process = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _check(
            "openclaw.node",
            PreflightStatus.FAIL,
            "Node.js version could not be inspected",
            role,
        )
    version_match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", process.stdout.strip())
    supported = (
        process.returncode == 0
        and version_match is not None
        and tuple(map(int, version_match.groups())) >= (22, 19, 0)
    )
    return _check(
        "openclaw.node",
        PreflightStatus.PASS if supported else PreflightStatus.FAIL,
        "Node.js 22.19.0 or newer is available"
        if supported
        else "OpenClaw requires Node.js 22.19.0 or newer",
        role,
    )


def _control_plane_client_checks(
    url: str,
    token_configured: bool,
    *,
    role: PreflightRole,
    environment_name: str,
) -> list[PreflightCheck]:
    parsed = urlsplit(url)
    valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    secure = valid and (
        parsed.scheme == "https"
        or parsed.hostname in LOOPBACK_HOSTS
        or environment_name in {"local", "test"}
    )
    return [
        _check(
            f"{role.value}.control-plane-url",
            PreflightStatus.PASS if secure else PreflightStatus.FAIL,
            "Control Plane URL is configured with an accepted transport"
            if secure
            else "a valid HTTPS Control Plane URL is required for a remote deployment",
            (role,),
        ),
        _check(
            f"{role.value}.api-token",
            PreflightStatus.PASS if token_configured else PreflightStatus.FAIL,
            "API token is configured" if token_configured else "API token is required",
            (role,),
        ),
    ]


async def _inspect_database(
    settings: Settings,
    project_root: Path,
    roles: tuple[PreflightRole, ...],
) -> list[PreflightCheck]:
    database_roles = tuple(role for role in roles if role in DATABASE_ROLES)
    engine = None
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            current_heads = await connection.run_sync(
                lambda sync_connection: set(
                    MigrationContext.configure(sync_connection).get_current_heads()
                )
            )
    except Exception as exc:
        return [
            _check(
                "database.connectivity",
                PreflightStatus.FAIL,
                f"database connection or query failed ({type(exc).__name__})",
                database_roles,
            )
        ]
    finally:
        if engine is not None:
            await engine.dispose()

    try:
        configuration = AlembicConfig(str(project_root / "alembic.ini"))
        configuration.set_main_option("script_location", str(project_root / "migrations"))
        expected_heads = set(ScriptDirectory.from_config(configuration).get_heads())
    except Exception as exc:
        return [
            _check(
                "database.connectivity",
                PreflightStatus.PASS,
                "database connection and query succeeded",
                database_roles,
            ),
            _check(
                "database.migrations",
                PreflightStatus.FAIL,
                f"migration metadata could not be loaded ({type(exc).__name__})",
                database_roles,
            ),
        ]
    migration_ready = current_heads == expected_heads
    return [
        _check(
            "database.connectivity",
            PreflightStatus.PASS,
            "database connection and query succeeded",
            database_roles,
        ),
        _check(
            "database.migrations",
            PreflightStatus.PASS if migration_ready else PreflightStatus.FAIL,
            "database is at the expected migration head"
            if migration_ready
            else "database migration heads do not match the application",
            database_roles,
        ),
    ]


def _check(
    key: str,
    status: PreflightStatus,
    detail: str,
    roles: tuple[PreflightRole, ...],
) -> PreflightCheck:
    return PreflightCheck(key=key, status=status, detail=detail, roles=roles)
