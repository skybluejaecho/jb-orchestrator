"""Shell-free Git process boundary for GitHub publication."""

import asyncio
import os
from pathlib import Path
from typing import Protocol


class GitHubGitError(RuntimeError):
    """A bounded Git command failed."""


class GitClient(Protocol):
    async def run(self, workspace: Path, *arguments: str) -> str: ...


class SubprocessGitClient:
    def __init__(self, executable: str = "git", *, timeout_seconds: float = 120.0) -> None:
        if not executable.strip() or timeout_seconds <= 0:
            raise ValueError("Git executable and positive timeout are required")
        self._executable = executable.strip()
        self._timeout_seconds = timeout_seconds

    async def run(self, workspace: Path, *arguments: str) -> str:
        environment = dict(os.environ)
        environment["GIT_TERMINAL_PROMPT"] = "0"
        process = await asyncio.create_subprocess_exec(
            self._executable,
            "-C",
            str(workspace),
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise GitHubGitError("Git command timed out") from exc
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise GitHubGitError(
                detail or f"Git command failed with exit code {process.returncode}"
            )
        return stdout.decode(errors="replace").strip()
