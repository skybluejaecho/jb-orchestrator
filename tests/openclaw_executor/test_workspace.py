import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from jb_openclaw_executor.workspace import (
    OpenClawWorkspaceError,
    OpenClawWorkspaceManager,
)

from tests.openclaw_executor.test_executor import task_claim


def _git(cwd: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
    )
    return result.stdout.strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "develop")
    _git(path, "config", "user.name", "JB Test")
    _git(path, "config", "user.email", "jb-test@example.invalid")
    (path / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    return path.resolve()


async def test_git_worktree_assignment_is_isolated_and_retry_stable(tmp_path: Path) -> None:
    repositories = tmp_path / "repositories"
    repositories.mkdir()
    repository = _repository(repositories / "project")
    workspace_root = tmp_path / "worktrees"
    claim = replace(
        task_claim(),
        configuration={
            "cwd": str(repository),
            "workspace_mode": "git_worktree",
            "workspace_base_ref": "develop",
        },
    )
    manager = OpenClawWorkspaceManager(
        workspace_root=workspace_root,
        repository_roots=(repositories,),
    )

    first = await manager.prepare(claim)
    second = await manager.prepare(claim)

    assert first == second
    assert first.path is not None
    assert Path(first.path).is_dir()
    assert Path(first.path) != repository
    assert claim.execution_id.hex[:12] in first.path
    assert first.branch == _git(Path(first.path), "branch", "--show-current")
    expected_commit = _git(repository, "rev-parse", "develop")
    assert first.base_ref == expected_commit
    assert _git(Path(first.path), "rev-parse", "HEAD") == expected_commit


async def test_parallel_nodes_receive_different_worktrees(tmp_path: Path) -> None:
    repositories = tmp_path / "repositories"
    repositories.mkdir()
    repository = _repository(repositories / "project")
    manager = OpenClawWorkspaceManager(
        workspace_root=tmp_path / "worktrees",
        repository_roots=(repositories,),
    )
    common = {
        "cwd": str(repository),
        "workspace_mode": "git_worktree",
        "workspace_base_ref": "develop",
    }
    first_claim = replace(task_claim(), node_key="implementation", configuration=common)
    second_claim = replace(task_claim(), node_key="verification", configuration=common)

    first = await manager.prepare(first_claim)
    second = await manager.prepare(second_claim)

    assert first.path != second.path
    assert first.branch != second.branch


async def test_git_worktree_rejects_repository_outside_allowlist(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "project")
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    claim = replace(
        task_claim(),
        configuration={
            "cwd": str(repository),
            "workspace_mode": "git_worktree",
            "workspace_base_ref": "develop",
        },
    )
    manager = OpenClawWorkspaceManager(
        workspace_root=tmp_path / "worktrees",
        repository_roots=(allowed,),
    )

    with pytest.raises(OpenClawWorkspaceError, match="outside"):
        await manager.prepare(claim)


async def test_shared_workspace_preserves_existing_behavior() -> None:
    claim = replace(task_claim(), configuration={"cwd": "C:/projects/shared"})
    manager = OpenClawWorkspaceManager(workspace_root=None, repository_roots=())

    assignment = await manager.prepare(claim)

    assert assignment.cwd == "C:/projects/shared"
    assert assignment.branch is None
