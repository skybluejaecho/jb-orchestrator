"""Executor entry-point factory."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from jb_openclaw_executor.bridge import OpenClawBridgeClient
from jb_openclaw_executor.executor import OpenClawExecutor
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.worker import TaskExecutor


class OpenClawExecutorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JB_OPENCLAW_", extra="ignore")

    bridge_path: Path = Path("tools/openclaw-gateway-spike/src/bridge.mjs")
    node_executable: str = "node"


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
    return OpenClawExecutor(service, bridge)
