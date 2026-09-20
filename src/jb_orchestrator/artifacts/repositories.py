"""Persistence port for immutable task artifacts."""

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from jb_orchestrator.artifacts.models import TaskArtifact


class TaskArtifactRepository(Protocol):
    async def add(self, artifact: TaskArtifact) -> None: ...

    async def list_for_execution(self, execution_id: UUID) -> list[TaskArtifact]: ...

    async def list_latest_for_nodes(
        self, execution_id: UUID, node_keys: Collection[str]
    ) -> list[TaskArtifact]: ...
