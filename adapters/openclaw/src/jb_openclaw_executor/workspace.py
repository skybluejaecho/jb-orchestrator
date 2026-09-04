"""Fail-closed Git worktree allocation for OpenClaw task nodes."""

import asyncio
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jb_orchestrator.external_executions import ExternalExecution
from jb_orchestrator.worker import TaskClaim

WORKTREE_MODE = "git_worktree"


class OpenClawWorkspaceError(RuntimeError):
    """A task workspace could not be allocated safely."""


@dataclass(frozen=True, slots=True)
class WorkspaceAssignment:
    cwd: str | None
    path: str | None = None
    repository_path: str | None = None
    branch: str | None = None
    base_ref: str | None = None
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceReview:
    path: str
    repository_path: str
    branch: str
    base_commit: str
    head_commit: str
    target_ref: str
    target_commit: str
    clean: bool
    merged: bool


class WorkspaceManager(Protocol):
    async def prepare(self, claim: TaskClaim) -> WorkspaceAssignment: ...


class OpenClawWorkspaceManager:
    def __init__(
        self,
        *,
        workspace_root: Path | None,
        repository_roots: tuple[Path, ...],
        git_executable: str = "git",
    ) -> None:
        self._workspace_root = workspace_root.resolve() if workspace_root else None
        self._repository_roots = tuple(path.resolve() for path in repository_roots)
        self._git_executable = git_executable

    async def prepare(self, claim: TaskClaim) -> WorkspaceAssignment:
        return await asyncio.to_thread(self._prepare_sync, claim)

    async def review(self, execution: ExternalExecution, *, merged_into: str) -> WorkspaceReview:
        return await asyncio.to_thread(self._review_sync, execution, merged_into)

    async def cleanup(self, execution: ExternalExecution, *, merged_into: str) -> WorkspaceReview:
        return await asyncio.to_thread(self._cleanup_sync, execution, merged_into)

    def _prepare_sync(self, claim: TaskClaim) -> WorkspaceAssignment:
        mode = _optional_string(claim.configuration, "workspace_mode") or "shared"
        source_value = _optional_string(claim.configuration, "cwd")
        if mode == "shared":
            return WorkspaceAssignment(cwd=source_value)
        if mode != WORKTREE_MODE:
            raise OpenClawWorkspaceError(f"unsupported OpenClaw workspace mode: {mode}")
        if source_value is None:
            raise OpenClawWorkspaceError("git_worktree mode requires node configuration cwd")
        base_ref = _optional_string(claim.configuration, "workspace_base_ref")
        if base_ref is None:
            raise OpenClawWorkspaceError(
                "git_worktree mode requires an explicit workspace_base_ref"
            )
        if self._workspace_root is None:
            raise OpenClawWorkspaceError("git_worktree mode requires JB_OPENCLAW_WORKSPACE_ROOT")
        if not self._repository_roots:
            raise OpenClawWorkspaceError("git_worktree mode requires JB_OPENCLAW_REPOSITORY_ROOTS")

        source = Path(source_value).resolve()
        repository = Path(self._git(source, "rev-parse", "--show-toplevel")).resolve()
        if source != repository:
            raise OpenClawWorkspaceError("configured cwd must be the Git repository root")
        if not any(repository.is_relative_to(root) for root in self._repository_roots):
            raise OpenClawWorkspaceError(
                f"repository is outside JB_OPENCLAW_REPOSITORY_ROOTS: {repository}"
            )
        workspace_root = self._workspace_root
        if workspace_root.is_relative_to(repository) or repository.is_relative_to(workspace_root):
            raise OpenClawWorkspaceError(
                "JB_OPENCLAW_WORKSPACE_ROOT and the source repository must not contain each other"
            )
        base_commit = self._git(
            repository,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        )

        slug = _slug(claim.node_key)
        execution_key = claim.execution_id.hex[:12]
        destination = (workspace_root / execution_key / f"{slug}-v{claim.visit_count}").resolve()
        if not destination.is_relative_to(workspace_root):
            raise OpenClawWorkspaceError("resolved worktree path escaped its configured root")
        branch = f"jb/{execution_key}/{slug}-v{claim.visit_count}"

        if destination.exists():
            actual_root = Path(self._git(destination, "rev-parse", "--show-toplevel")).resolve()
            actual_branch = self._git(destination, "branch", "--show-current")
            if actual_root != destination or actual_branch != branch:
                raise OpenClawWorkspaceError(
                    f"existing workspace does not match its deterministic assignment: {destination}"
                )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            branch_exists = (
                self._git_returncode(
                    repository,
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{branch}",
                )
                == 0
            )
            arguments = ["worktree", "add"]
            if branch_exists:
                arguments.extend([str(destination), branch])
            else:
                arguments.extend(["-b", branch, str(destination), base_commit])
            self._git(repository, *arguments)

        return WorkspaceAssignment(
            cwd=str(destination),
            path=str(destination),
            repository_path=str(repository),
            branch=branch,
            base_ref=base_commit,
            scope=self.scope,
        )

    @property
    def scope(self) -> str | None:
        if self._workspace_root is None:
            return None
        capability_paths = (self._workspace_root, *sorted(self._repository_roots))
        encoded = "\n".join(os.path.normcase(str(path)) for path in capability_paths).encode(
            "utf-8"
        )
        return f"git-worktree:{hashlib.sha256(encoded).hexdigest()}"

    def _review_sync(self, execution: ExternalExecution, merged_into: str) -> WorkspaceReview:
        repository, workspace, branch, base_commit = self._workspace_record(execution)
        if not workspace.is_dir():
            raise OpenClawWorkspaceError(f"worktree does not exist: {workspace}")
        actual_root = Path(self._git(workspace, "rev-parse", "--show-toplevel")).resolve()
        actual_branch = self._git(workspace, "branch", "--show-current")
        if actual_root != workspace or actual_branch != branch:
            raise OpenClawWorkspaceError("worktree no longer matches its durable assignment")
        head_commit = self._git(workspace, "rev-parse", "HEAD")
        target_ref = merged_into.strip()
        if not target_ref:
            raise OpenClawWorkspaceError("merged-into ref must not be empty")
        target_commit = self._git(
            repository,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{target_ref}^{{commit}}",
        )
        clean = not self._git(workspace, "status", "--porcelain", "--untracked-files=all")
        merged = (
            self._git_returncode(
                repository, "merge-base", "--is-ancestor", head_commit, target_commit
            )
            == 0
        )
        return WorkspaceReview(
            path=str(workspace),
            repository_path=str(repository),
            branch=branch,
            base_commit=base_commit,
            head_commit=head_commit,
            target_ref=target_ref,
            target_commit=target_commit,
            clean=clean,
            merged=merged,
        )

    def _cleanup_sync(self, execution: ExternalExecution, merged_into: str) -> WorkspaceReview:
        if not execution.is_terminal:
            raise OpenClawWorkspaceError("worktree cleanup requires a terminal external execution")
        repository, workspace, branch, base_commit = self._workspace_record(execution)
        delete_branch = True
        if workspace.exists():
            review = self._review_sync(execution, merged_into)
            if not review.clean:
                raise OpenClawWorkspaceError("worktree has uncommitted changes")
            if not review.merged:
                raise OpenClawWorkspaceError(
                    f"workspace branch is not merged into {review.target_ref}"
                )
            self._git(repository, "worktree", "remove", str(workspace))
        else:
            target_ref = merged_into.strip()
            if not target_ref:
                raise OpenClawWorkspaceError("merged-into ref must not be empty")
            target_commit = self._git(
                repository,
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{target_ref}^{{commit}}",
            )
            branch_exists = (
                self._git_returncode(
                    repository,
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{branch}",
                )
                == 0
            )
            head_commit = (
                self._git(
                    repository,
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"refs/heads/{branch}^{{commit}}",
                )
                if branch_exists
                else base_commit
            )
            merged = (
                self._git_returncode(
                    repository, "merge-base", "--is-ancestor", head_commit, target_commit
                )
                == 0
            )
            if not merged:
                raise OpenClawWorkspaceError(f"workspace branch is not merged into {target_ref}")
            review = WorkspaceReview(
                path=str(workspace),
                repository_path=str(repository),
                branch=branch,
                base_commit=base_commit,
                head_commit=head_commit,
                target_ref=target_ref,
                target_commit=target_commit,
                clean=True,
                merged=True,
            )
            delete_branch = branch_exists
        if delete_branch:
            self._git(
                repository,
                "update-ref",
                "-d",
                f"refs/heads/{branch}",
                review.head_commit,
            )
        return review

    def _workspace_record(self, execution: ExternalExecution) -> tuple[Path, Path, str, str]:
        values = (
            execution.workspace_repository_path,
            execution.workspace_path,
            execution.workspace_branch,
            execution.workspace_base_ref,
        )
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise OpenClawWorkspaceError(
                "external execution has no complete managed workspace assignment"
            )
        if self._workspace_root is None or not self._repository_roots:
            raise OpenClawWorkspaceError("managed workspace roots are not configured")
        repository = Path(str(values[0])).resolve()
        workspace = Path(str(values[1])).resolve()
        branch = str(values[2])
        base_commit = str(values[3])
        if not any(repository.is_relative_to(root) for root in self._repository_roots):
            raise OpenClawWorkspaceError("stored repository is outside the configured roots")
        if not workspace.is_relative_to(self._workspace_root):
            raise OpenClawWorkspaceError("stored worktree is outside the configured workspace root")
        actual_repository = Path(self._git(repository, "rev-parse", "--show-toplevel")).resolve()
        if actual_repository != repository:
            raise OpenClawWorkspaceError("stored repository path is not its Git top level")
        return repository, workspace, branch, base_commit

    def _git(self, cwd: Path, *arguments: str) -> str:
        try:
            result = subprocess.run(
                [self._git_executable, "-C", str(cwd), *arguments],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", None)
            suffix = f": {str(detail).strip()}" if detail else ""
            raise OpenClawWorkspaceError(
                f"Git workspace command failed ({' '.join(arguments)}){suffix}"
            ) from exc
        return result.stdout.strip()

    def _git_returncode(self, cwd: Path, *arguments: str) -> int:
        try:
            result = subprocess.run(
                [self._git_executable, "-C", str(cwd), *arguments],
                check=False,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OpenClawWorkspaceError("Git executable is unavailable") from exc
        if result.returncode not in {0, 1}:
            raise OpenClawWorkspaceError(f"Git workspace lookup failed: {result.stderr.strip()}")
        return result.returncode


def _optional_string(configuration: dict[str, Any], key: str) -> str | None:
    value = configuration.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.").lower()
    if not normalized:
        raise OpenClawWorkspaceError("node key cannot produce a safe workspace name")
    return normalized[:48]
