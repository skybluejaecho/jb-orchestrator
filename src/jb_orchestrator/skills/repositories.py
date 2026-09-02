"""Persistence ports for the skill catalog."""

from typing import Protocol

from jb_orchestrator.skills.models import SkillDefinition


class SkillRepository(Protocol):
    async def add(self, skill: SkillDefinition) -> None: ...

    async def get(self, key: str, version: int | None = None) -> SkillDefinition | None: ...

    async def list_latest(self) -> list[SkillDefinition]: ...
