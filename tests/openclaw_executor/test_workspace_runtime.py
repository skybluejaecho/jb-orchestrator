import subprocess
from dataclasses import replace
from pathlib import Path

from jb_openclaw_executor.workspace import OpenClawWorkspaceManager
from jb_openclaw_executor.workspace_runtime import WorkspaceOperationRuntime

from jb_orchestrator.application import ExternalExecutionService, WorkspaceOperationService
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.workspace_operations import WorkspaceOperationKind, WorkspaceOperationStatus
from tests.openclaw_executor.test_executor import task_claim
from tests.support import MemoryStore, MemoryUnitOfWork


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


async def test_runtime_inspects_then_releases_merged_workspace(tmp_path: Path) -> None:
    repositories = tmp_path / "repositories"
    repository = repositories / "project"
    repository.mkdir(parents=True)
    _git(repository, "init", "-b", "develop")
    _git(repository, "config", "user.name", "JB Test")
    _git(repository, "config", "user.email", "jb-test@example.invalid")
    (repository / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "initial")
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
    workspace = Path(assignment.path or "")
    (workspace / "result.txt").write_text("done\n", encoding="utf-8")
    _git(workspace, "add", "result.txt")
    _git(workspace, "commit", "-m", "result")

    store = MemoryStore()
    executions = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    operations = WorkspaceOperationService(lambda: MemoryUnitOfWork(store))
    execution = await executions.prepare(
        claim,
        session_key="agent:implementation:1",
        agent_id="implementation",
        workspace_path=assignment.path,
        workspace_repository_path=assignment.repository_path,
        workspace_branch=assignment.branch,
        workspace_base_ref=assignment.base_ref,
        workspace_scope=assignment.scope,
    )
    await executions.finish(claim.idempotency_key, ExternalExecutionStatus.SUCCEEDED)
    runtime = WorkspaceOperationRuntime("workspace-a", operations, executions, manager)

    inspect, _ = await operations.request(
        execution.id,
        kind=WorkspaceOperationKind.INSPECT,
        target_ref="develop",
        idempotency_key="inspect-1",
        requested_by="jarvis",
    )
    assert await runtime.run_once()
    assert store.workspace_operations[inspect.id].result is not None
    assert store.workspace_operations[inspect.id].result["merged"] is False

    _git(repository, "merge", "--ff-only", assignment.branch or "")
    cleanup, _ = await operations.request(
        execution.id,
        kind=WorkspaceOperationKind.CLEANUP,
        target_ref="develop",
        idempotency_key="cleanup-1",
        requested_by="jarvis",
        confirmation=str(execution.id),
    )
    assert await runtime.run_once()

    completed = store.workspace_operations[cleanup.id]
    assert completed.status is WorkspaceOperationStatus.SUCCEEDED
    assert completed.result is not None
    assert completed.result["status"] == "released"
    assert not workspace.exists()
    assert (await executions.get_by_id(execution.id)).workspace_released_at is not None
