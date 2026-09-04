"""Executor entry-point factory."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from jb_openclaw_executor.bridge import OpenClawBridgeClient
from jb_openclaw_executor.executor import OpenClawExecutor
from jb_openclaw_executor.workspace import OpenClawWorkspaceManager
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.worker import TaskExecutor


class OpenClawExecutorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JB_OPENCLAW_", extra="ignore")

    bridge_path: Path = Path("tools/openclaw-gateway-spike/src/bridge.mjs")
    node_executable: str = "node"
    workspace_root: Path | None = None
    repository_roots: tuple[Path, ...] = ()
    git_executable: str = "git"


def create_executor() -> TaskExecutor:
    """Build the optional adapter using process and database configuration."""

    settings = get_settings()
    adapter_settings = OpenClawExecutorSettings()
    session_factory = create_session_factory(settings)
    service = ExternalExecutionService(lambda: SqlAlchemyUnitOfWork(session_factory))
    bridge = OpenClawBridgeClient(
        adapter_settings.bridge_path,
        node_executable=adapter_settings.node_executable,
    )
    workspace = OpenClawWorkspaceManager(
        workspace_root=adapter_settings.workspace_root,
        repository_roots=adapter_settings.repository_roots,
        git_executable=adapter_settings.git_executable,
    )
    return OpenClawExecutor(service, bridge, workspace=workspace)
