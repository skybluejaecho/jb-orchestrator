"""Fail-closed Git worktree allocation for OpenClaw task nodes."""

import asyncio
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jb_orchestrator.worker import TaskClaim

WORKTREE_MODE = "git_worktree"


class OpenClawWorkspaceError(RuntimeError):
    """A task workspace could not be allocated safely."""


@dataclass(frozen=True, slots=True)
class WorkspaceAssignment:
    cwd: str | None
    path: str | None = None
    branch: str | None = None
    base_ref: str | None = None


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
            branch=branch,
            base_ref=base_commit,
        )

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
