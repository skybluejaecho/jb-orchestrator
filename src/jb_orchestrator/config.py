"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JB_",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    control_plane_url: str = "http://127.0.0.1:8000"
    database_url: str = (
        "postgresql+asyncpg://jb_orchestrator:jb_orchestrator@localhost:5432/jb_orchestrator"
    )
    skill_cache_dir: Path = Path(".jb-orchestrator/cache/skills")
    skill_local_root: Path = Path("skills")
    skill_allowed_remote_hosts: frozenset[str] = frozenset()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""

    return Settings()
