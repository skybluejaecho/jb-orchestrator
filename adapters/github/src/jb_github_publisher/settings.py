"""Environment-backed GitHub publisher configuration."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubPublisherSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JB_GITHUB_", extra="ignore")

    token: SecretStr | None = None
    workspace_roots: tuple[Path, ...] = ()
    api_url: str = "https://api.github.com"
    web_host: str = "github.com"
    api_version: str = "2026-03-10"
    git_executable: str = "git"
    remote_name: str = "origin"
    git_timeout_seconds: float = Field(default=120.0, gt=0)
    http_timeout_seconds: float = Field(default=30.0, gt=0)
    allow_insecure_loopback: bool = False
