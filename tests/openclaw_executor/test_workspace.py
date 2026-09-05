import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from jb_openclaw_executor.workspace import (
    OpenClawWorkspaceError,
    OpenClawWorkspaceManager,
    WorkspaceAssignment,
)

from jb_orchestrator.external_executions import ExternalExecution, ExternalExecutionStatus
from jb_orchestrator.worker import TaskClaim
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


def _external_execution(claim: TaskClaim, assignment: WorkspaceAssignment) -> ExternalExecution:
    return ExternalExecution(
        execution_id=claim.execution_id,
        run_id=claim.run_id,
        node_key=claim.node_key,
        executor_key="openclaw",
        idempotency_key=claim.idempotency_key,
        external_session_key="agent:implementation:execution",
        external_run_id="openclaw-run-1",
        status=ExternalExecutionStatus.SUCCEEDED,
        workspace_path=assignment.path,
        workspace_repository_path=assignment.repository_path,
        workspace_branch=assignment.branch,
        workspace_base_ref=assignment.base_ref,
        workspace_scope=assignment.scope,
    )


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
    assert first.scope == manager.scope
    assert first.scope is not None
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


async def test_cleanup_requires_clean_branch_merged_into_target(tmp_path: Path) -> None:
    repositories = tmp_path / "repositories"
    repositories.mkdir()
    repository = _repository(repositories / "project")
    manager = OpenClawWorkspaceManager(
        workspace_root=tmp_path / "worktrees",
        repository_roots=(repositories,),
    )
    claim = replace(
        task_claim(),
        configuration={
            "cwd": str(repository),
            "workspace_mode": "git_worktree",
            "workspace_base_ref": "develop",
        },
    )
    assignment = await manager.prepare(claim)
    assert assignment.path is not None
    workspace = Path(assignment.path)
    (workspace / "result.txt").write_text("done\n", encoding="utf-8")
    execution = _external_execution(claim, assignment)

    with pytest.raises(OpenClawWorkspaceError, match="uncommitted"):
        await manager.cleanup(execution, merged_into="develop")

    _git(workspace, "add", "result.txt")
    _git(workspace, "commit", "-m", "complete isolated work")
    with pytest.raises(OpenClawWorkspaceError, match="not merged"):
        await manager.cleanup(execution, merged_into="develop")

    assert assignment.branch is not None
    _git(repository, "merge", "--ff-only", assignment.branch)
    review = await manager.review(execution, merged_into="develop")
    assert review.clean is True
    assert review.merged is True

    released = await manager.cleanup(execution, merged_into="develop")

    assert released.head_commit == _git(repository, "rev-parse", "develop")
    assert not workspace.exists()
    branch_check = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{assignment.branch}",
        ],
        check=False,
        capture_output=True,
    )
    assert branch_check.returncode == 1
