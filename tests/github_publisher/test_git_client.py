import subprocess
from pathlib import Path

import pytest
from jb_github_publisher.git_client import GitHubGitError, SubprocessGitClient


def git(workspace: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(workspace), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


async def test_subprocess_git_runs_without_a_shell(tmp_path: Path) -> None:
    git(tmp_path, "init")

    result = await SubprocessGitClient().run(tmp_path, "rev-parse", "--show-toplevel")

    assert Path(result).resolve() == tmp_path.resolve()


async def test_subprocess_git_returns_sanitized_command_failure(tmp_path: Path) -> None:
    git(tmp_path, "init")

    with pytest.raises(GitHubGitError, match="unknown revision"):
        await SubprocessGitClient().run(tmp_path, "rev-parse", "missing-ref")
