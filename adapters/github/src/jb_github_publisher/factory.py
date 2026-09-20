"""Installed GitHub publisher entry-point factory."""

import os

from jb_github_publisher.api import GitHubApiClient
from jb_github_publisher.git_client import SubprocessGitClient
from jb_github_publisher.publisher import GitHubPublisher
from jb_github_publisher.settings import GitHubPublisherSettings
from jb_orchestrator.scm import ScmPublisher


class GitHubPublisherConfigurationError(ValueError):
    """Required adapter-owned credentials or filesystem scopes are missing."""


def create_publisher() -> ScmPublisher:
    """Build a GitHub publisher from adapter-owned environment settings."""

    settings = GitHubPublisherSettings()
    if settings.token is None:
        raise GitHubPublisherConfigurationError("JB_GITHUB_TOKEN is required")
    if not settings.workspace_roots:
        raise GitHubPublisherConfigurationError("JB_GITHUB_WORKSPACE_ROOTS is required")
    if settings.allow_insecure_loopback and os.environ.get("JB_ENVIRONMENT") != "test":
        raise GitHubPublisherConfigurationError(
            "JB_GITHUB_ALLOW_INSECURE_LOOPBACK requires JB_ENVIRONMENT=test"
        )
    return GitHubPublisher(
        GitHubApiClient(
            settings.token.get_secret_value(),
            api_url=settings.api_url,
            api_version=settings.api_version,
            timeout_seconds=settings.http_timeout_seconds,
            allow_insecure_loopback=settings.allow_insecure_loopback,
        ),
        SubprocessGitClient(settings.git_executable, timeout_seconds=settings.git_timeout_seconds),
        workspace_roots=settings.workspace_roots,
        web_host=settings.web_host,
        remote_name=settings.remote_name,
    )
