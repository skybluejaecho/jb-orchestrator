from pathlib import Path

import httpx
import pytest
from jb_github_publisher.api import GitHubApiClient
from jb_github_publisher.publisher import GitHubPublicationError, GitHubPublisher

from jb_orchestrator.scm import ScmPublicationRequest


class FakeGit:
    def __init__(
        self,
        workspace: Path,
        *,
        branch: str = "feature/work",
        status: str = "",
        remote_url: str = "git@github.com:example/project.git",
    ) -> None:
        self.commands: list[tuple[str, ...]] = []
        self._responses = {
            ("rev-parse", "--show-toplevel"): str(workspace.resolve()),
            ("branch", "--show-current"): branch,
            ("status", "--porcelain"): status,
            ("remote", "get-url", "origin"): remote_url,
            ("rev-parse", "HEAD"): "a" * 40,
        }

    async def run(self, workspace: Path, *arguments: str) -> str:
        self.commands.append(arguments)
        return self._responses.get(arguments, "")


def request(workspace: Path) -> ScmPublicationRequest:
    return ScmPublicationRequest(
        repository="https://github.com/example/project.git",
        workspace_path=str(workspace),
        source_branch="feature/work",
        target_branch="develop",
        title="Review work",
        body="Details",
        idempotency_key="publish-1",
    )


def api(handler: httpx.MockTransport) -> GitHubApiClient:
    return GitHubApiClient(
        "secret-token",
        api_url="https://api.github.test",
        transport=handler,
    )


async def test_publisher_validates_pushes_exact_head_and_creates_review(tmp_path: Path) -> None:
    workspace = tmp_path / "worktrees" / "task"
    workspace.mkdir(parents=True)
    git = FakeGit(workspace)
    requests: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        if http_request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(
            201,
            json={
                "number": 52,
                "html_url": "https://github.com/example/project/pull/52",
                "head": {"ref": "feature/work"},
                "base": {"ref": "develop"},
            },
        )

    publisher = GitHubPublisher(
        api(httpx.MockTransport(handler)),
        git,
        workspace_roots=(tmp_path / "worktrees",),
    )

    result = await publisher.publish_review(request(workspace))

    assert result.review_id == "52"
    assert result.review_url == "https://github.com/example/project/pull/52"
    assert (
        "push",
        "--porcelain",
        "origin",
        f"{'a' * 40}:refs/heads/feature/work",
    ) in git.commands
    assert [item.method for item in requests] == ["GET", "POST"]


@pytest.mark.parametrize(
    ("git_kwargs", "message"),
    [
        ({"branch": "feature/other"}, "branch does not match"),
        ({"status": " M modified.py"}, "workspace must be clean"),
        (
            {"remote_url": "git@github.com:another/project.git"},
            "remote does not match",
        ),
    ],
)
async def test_publisher_rejects_unsafe_git_state_before_push(
    tmp_path: Path, git_kwargs: dict[str, str], message: str
) -> None:
    workspace = tmp_path / "worktrees" / "task"
    workspace.mkdir(parents=True)
    git = FakeGit(workspace, **git_kwargs)
    publisher = GitHubPublisher(
        api(httpx.MockTransport(lambda request: httpx.Response(500))),
        git,
        workspace_roots=(tmp_path / "worktrees",),
    )

    with pytest.raises(GitHubPublicationError, match=message):
        await publisher.publish_review(request(workspace))

    assert not any(command[0] == "push" for command in git.commands)


async def test_publisher_rejects_workspace_outside_allowlist(tmp_path: Path) -> None:
    workspace = tmp_path / "untrusted" / "task"
    workspace.mkdir(parents=True)
    git = FakeGit(workspace)
    publisher = GitHubPublisher(
        api(httpx.MockTransport(lambda request: httpx.Response(500))),
        git,
        workspace_roots=(tmp_path / "allowed",),
    )

    with pytest.raises(GitHubPublicationError, match="outside configured roots"):
        await publisher.publish_review(request(workspace))

    assert git.commands == []
