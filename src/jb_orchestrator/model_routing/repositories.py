"""Persistence ports for versioned model profiles."""

from typing import Protocol

from jb_orchestrator.model_routing.models import ModelProfile


class ModelProfileRepository(Protocol):
    async def add(self, profile: ModelProfile) -> None: ...

    async def get(self, key: str, version: int | None = None) -> ModelProfile | None: ...

    async def list_latest(self) -> list[ModelProfile]: ...
