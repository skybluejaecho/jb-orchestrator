import subprocess
from pathlib import Path

import httpx
import pytest
from jb_github_publisher.api import GitHubApiClient, GitHubApiError
from jb_github_publisher.git_client import SubprocessGitClient
from jb_github_publisher.publisher import GitHubPublisher
from jb_github_publisher.repository import GitHubRepository

from jb_orchestrator.scm import ScmPublicationRequest
from jb_orchestrator.system_smoke_scm import GitHubApiStub, prepare_scm_repository


def test_scm_repository_rewrites_github_push_to_local_bare_remote(tmp_path: Path) -> None:
    fixture = prepare_scm_repository(tmp_path, "fixture")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=fixture.workspace,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        [
            "git",
            "push",
            "origin",
            f"{head}:refs/heads/{fixture.source_branch}",
        ],
        cwd=fixture.workspace,
        capture_output=True,
        text=True,
        check=True,
    )
    remote = tmp_path / "scm-remote.git"
    published = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", fixture.source_branch],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert published == head


def test_github_api_stub_validates_and_records_pull_request() -> None:
    with GitHubApiStub("feature/smoke", "develop") as stub:
        response = httpx.post(
            f"{stub.api_url}/repos/system-smoke/repository/pulls",
            json={"head": "feature/smoke", "base": "develop"},
        )

    assert response.status_code == 201
    assert response.json()["number"] == 53
    assert stub.created is True


async def test_real_github_client_uses_loopback_stub_contract() -> None:
    with GitHubApiStub("feature/smoke", "develop") as stub:
        pull_request = await GitHubApiClient(
            "smoke-token",
            api_url=stub.api_url,
            allow_insecure_loopback=True,
        ).find_or_create_pull_request(
            GitHubRepository("system-smoke", "repository"),
            source_branch="feature/smoke",
            target_branch="develop",
            title="Smoke",
            body="Smoke body",
        )

    assert pull_request.number == 53
    assert stub.created is True


async def test_real_github_publisher_pushes_and_creates_review(tmp_path: Path) -> None:
    fixture = prepare_scm_repository(tmp_path, "publisher")
    with GitHubApiStub(fixture.source_branch, fixture.target_branch) as stub:
        publisher = GitHubPublisher(
            GitHubApiClient(
                "smoke-token",
                api_url=stub.api_url,
                allow_insecure_loopback=True,
            ),
            SubprocessGitClient(timeout_seconds=10),
            workspace_roots=(tmp_path,),
            web_host="github.local",
        )
        result = await publisher.publish_review(
            ScmPublicationRequest(
                repository=fixture.repository_url,
                workspace_path=str(fixture.workspace),
                source_branch=fixture.source_branch,
                target_branch=fixture.target_branch,
                title="Smoke publication",
                body="Smoke body",
                idempotency_key="smoke-publication",
            )
        )

    assert result.review_url == "https://github.local/system-smoke/repository/pull/53"
    assert stub.created is True


async def test_github_api_stub_can_fail_first_create_for_retry_smoke() -> None:
    repository = GitHubRepository("system-smoke", "repository")
    with GitHubApiStub("feature/smoke", "develop", fail_first_create=True) as stub:
        client = GitHubApiClient(
            "smoke-token",
            api_url=stub.api_url,
            allow_insecure_loopback=True,
        )
        with pytest.raises(GitHubApiError, match="HTTP 503"):
            await client.find_or_create_pull_request(
                repository,
                source_branch="feature/smoke",
                target_branch="develop",
                title="Smoke",
                body="",
            )
        result = await client.find_or_create_pull_request(
            repository,
            source_branch="feature/smoke",
            target_branch="develop",
            title="Smoke",
            body="",
        )

    assert result.number == 53
    assert stub.create_attempts == 2
