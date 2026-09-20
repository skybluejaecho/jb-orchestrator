"""Reproducible local release-readiness checks."""

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReleaseCheckError(RuntimeError):
    """A release prerequisite or quality gate failed."""


@dataclass(frozen=True, slots=True)
class ReleaseCheckStep:
    name: str
    command: tuple[str, ...]
    working_directory: Path


@dataclass(frozen=True, slots=True)
class ReleaseCheckResult:
    checks: tuple[str, ...]
    duration_seconds: float
    system_smoke_included: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "checks": list(self.checks),
            "duration_seconds": round(self.duration_seconds, 3),
            "status": "ready",
            "system_smoke_included": self.system_smoke_included,
        }


def release_check_steps(
    project_root: Path, *, include_system_smoke: bool
) -> tuple[ReleaseCheckStep, ...]:
    """Return the ordered, shared release gate definition."""

    jarvis_root = project_root / "apps" / "jarvis"
    openclaw_contract_root = project_root / "tools" / "openclaw-gateway-spike"
    steps = [
        ReleaseCheckStep("python-lock", ("uv", "lock", "--check"), project_root),
        ReleaseCheckStep("python-lint", ("uv", "run", "ruff", "check", "."), project_root),
        ReleaseCheckStep(
            "python-format", ("uv", "run", "ruff", "format", "--check", "."), project_root
        ),
        ReleaseCheckStep("python-types", ("uv", "run", "mypy"), project_root),
        ReleaseCheckStep("python-tests", ("uv", "run", "pytest"), project_root),
        ReleaseCheckStep("jarvis-format", ("npm", "run", "format:check"), jarvis_root),
        ReleaseCheckStep("jarvis-lint", ("npm", "run", "lint"), jarvis_root),
        ReleaseCheckStep("jarvis-tests", ("npm", "test"), jarvis_root),
        ReleaseCheckStep("jarvis-build", ("npm", "run", "build"), jarvis_root),
        ReleaseCheckStep("openclaw-contract", ("npm", "test"), openclaw_contract_root),
    ]
    if include_system_smoke:
        steps.extend(
            [
                ReleaseCheckStep(
                    "database-migrations", ("uv", "run", "alembic", "upgrade", "head"), project_root
                ),
                ReleaseCheckStep(
                    "system-smoke",
                    (
                        "uv",
                        "run",
                        "--with-editable",
                        ".",
                        "--with-editable",
                        "adapters/github",
                        "--with-editable",
                        "adapters/webhook",
                        "--with-editable",
                        "tools/system-smoke-executor",
                        "jb",
                        "system",
                        "smoke",
                    ),
                    project_root,
                ),
            ]
        )
    return tuple(steps)


def run_release_check(
    project_root: Path,
    *,
    include_system_smoke: bool = False,
    timeout_seconds: float = 900.0,
) -> ReleaseCheckResult:
    """Run every release gate in a stable order and stop on the first failure."""

    root = project_root.resolve()
    _validate_project_root(root)
    if timeout_seconds <= 0:
        raise ReleaseCheckError("release check timeout must be greater than zero")
    if include_system_smoke and os.environ.get("JB_ENVIRONMENT") != "test":
        raise ReleaseCheckError(
            "full release check requires JB_ENVIRONMENT=test and a disposable database"
        )

    started_at = time.monotonic()
    completed: list[str] = []
    executables: dict[str, str] = {}
    for step in release_check_steps(root, include_system_smoke=include_system_smoke):
        executable_name = step.command[0]
        executable = executables.get(executable_name)
        if executable is None:
            executable = shutil.which(executable_name)
            if executable is None:
                raise ReleaseCheckError(
                    f"{step.name} cannot start because {executable_name} is not installed"
                )
            executables[executable_name] = executable
        command = [executable, *step.command[1:]]
        try:
            process = subprocess.run(
                command,
                cwd=step.working_directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ReleaseCheckError(
                f"{step.name} cannot start because {executable_name} is not installed"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ReleaseCheckError(
                f"{step.name} exceeded the {timeout_seconds:g} second timeout"
            ) from exc
        if process.returncode != 0:
            output = "\n".join(
                line
                for line in (process.stdout + process.stderr).splitlines()[-40:]
                if line.strip()
            )
            detail = f"\n{output}" if output else ""
            raise ReleaseCheckError(
                f"{step.name} failed with exit code {process.returncode}{detail}"
            )
        completed.append(step.name)

    return ReleaseCheckResult(
        checks=tuple(completed),
        duration_seconds=time.monotonic() - started_at,
        system_smoke_included=include_system_smoke,
    )


def _validate_project_root(project_root: Path) -> None:
    required_paths = (
        project_root / "pyproject.toml",
        project_root / "uv.lock",
        project_root / "apps" / "jarvis" / "package.json",
        project_root / "tools" / "openclaw-gateway-spike" / "package.json",
    )
    missing = [str(path.relative_to(project_root)) for path in required_paths if not path.is_file()]
    if missing:
        raise ReleaseCheckError(f"invalid project root; missing: {', '.join(missing)}")
