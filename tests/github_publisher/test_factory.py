from pathlib import Path

import pytest
from jb_github_publisher.factory import (
    GitHubPublisherConfigurationError,
    create_publisher,
)
from jb_github_publisher.publisher import GitHubPublisher


def test_factory_requires_adapter_owned_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JB_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("JB_GITHUB_WORKSPACE_ROOTS", '["C:/worktrees"]')

    with pytest.raises(GitHubPublisherConfigurationError, match="TOKEN"):
        create_publisher()


def test_factory_requires_workspace_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JB_GITHUB_TOKEN", "secret-token")
    monkeypatch.delenv("JB_GITHUB_WORKSPACE_ROOTS", raising=False)

    with pytest.raises(GitHubPublisherConfigurationError, match="WORKSPACE_ROOTS"):
        create_publisher()


def test_factory_builds_installed_adapter_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JB_GITHUB_TOKEN", "secret-token")
    monkeypatch.setenv("JB_GITHUB_WORKSPACE_ROOTS", f'["{tmp_path.as_posix()}"]')

    assert isinstance(create_publisher(), GitHubPublisher)


def test_factory_rejects_insecure_loopback_outside_test_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JB_ENVIRONMENT", "local")
    monkeypatch.setenv("JB_GITHUB_TOKEN", "secret-token")
    monkeypatch.setenv("JB_GITHUB_WORKSPACE_ROOTS", f'["{tmp_path.as_posix()}"]')
    monkeypatch.setenv("JB_GITHUB_ALLOW_INSECURE_LOOPBACK", "true")

    with pytest.raises(GitHubPublisherConfigurationError, match="JB_ENVIRONMENT=test"):
        create_publisher()
