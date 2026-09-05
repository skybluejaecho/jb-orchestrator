"""GitHub implementation of the provider-neutral SCM publisher port."""

from pathlib import Path
from urllib.parse import urlparse

from jb_github_publisher.api import GitHubApiClient
from jb_github_publisher.git_client import GitClient
from jb_github_publisher.repository import parse_github_repository
from jb_orchestrator.scm import ScmPublicationRequest, ScmPublicationResult


class GitHubPublicationError(RuntimeError):
    """A publication request violates the adapter safety boundary."""


class GitHubPublisher:
    def __init__(
        self,
        api: GitHubApiClient,
        git: GitClient,
        *,
        workspace_roots: tuple[Path, ...],
        web_host: str = "github.com",
        remote_name: str = "origin",
    ) -> None:
        if not workspace_roots:
            raise ValueError("GitHub publisher requires at least one workspace root")
        if not web_host.strip() or not remote_name.strip():
            raise ValueError("GitHub web host and remote name must not be empty")
        self._api = api
        self._git = git
        self._workspace_roots = tuple(root.resolve() for root in workspace_roots)
        self._web_host = web_host.strip().lower()
        self._remote_name = remote_name.strip()

    async def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult:
        repository = parse_github_repository(request.repository, web_host=self._web_host)
        workspace = self._trusted_workspace(request.workspace_path)
        top_level = Path(await self._git.run(workspace, "rev-parse", "--show-toplevel")).resolve()
        if top_level != workspace:
            raise GitHubPublicationError("workspace path is not the Git worktree root")
        await self._git.run(workspace, "check-ref-format", f"refs/heads/{request.source_branch}")
        await self._git.run(workspace, "check-ref-format", f"refs/heads/{request.target_branch}")
        current_branch = await self._git.run(workspace, "branch", "--show-current")
        if current_branch != request.source_branch:
            raise GitHubPublicationError("workspace branch does not match publication source")
        if await self._git.run(workspace, "status", "--porcelain"):
            raise GitHubPublicationError("workspace must be clean before publication")
        remote_url = await self._git.run(workspace, "remote", "get-url", self._remote_name)
        remote_repository = parse_github_repository(remote_url, web_host=self._web_host)
        if remote_repository.slug.casefold() != repository.slug.casefold():
            raise GitHubPublicationError("Git remote does not match publication repository")
        head_commit = await self._git.run(workspace, "rev-parse", "HEAD")
        await self._git.run(
            workspace,
            "push",
            "--porcelain",
            self._remote_name,
            f"{head_commit}:refs/heads/{request.source_branch}",
        )
        pull_request = await self._api.find_or_create_pull_request(
            repository,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            title=request.title,
            body=request.body,
        )
        if urlparse(pull_request.html_url).hostname != self._web_host:
            raise GitHubPublicationError("GitHub review URL host does not match configured host")
        return ScmPublicationResult(
            provider="github",
            repository=request.repository,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            review_url=pull_request.html_url,
            review_id=str(pull_request.number),
        )

    def _trusted_workspace(self, value: str) -> Path:
        workspace = Path(value).resolve()
        if not workspace.is_dir():
            raise GitHubPublicationError("managed workspace directory does not exist")
        if not any(
            workspace == root or root in workspace.parents for root in self._workspace_roots
        ):
            raise GitHubPublicationError("managed workspace is outside configured roots")
        return workspace
