"""Safe materialization of the packaged orchestration starter kit."""

from __future__ import annotations

import shutil
import tempfile
from importlib.resources import as_file, files
from pathlib import Path


class StarterKitError(RuntimeError):
    """The starter kit cannot be created without overwriting local data."""


def initialize_starter_kit(destination: Path) -> Path:
    """Atomically copy the packaged starter kit into a new directory."""

    resolved = destination.resolve()
    if resolved.exists():
        raise StarterKitError(f"starter destination already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{resolved.name}-", dir=resolved.parent)).resolve()
    try:
        template = files("jb_orchestrator.templates").joinpath("starter_kit")
        with as_file(template) as source:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
        temporary.replace(resolved)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return resolved
