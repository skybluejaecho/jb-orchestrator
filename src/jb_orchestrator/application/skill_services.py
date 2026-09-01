"""Skill catalog use cases."""

from collections.abc import Callable

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.skills import SkillDefinition


class SkillCatalogService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def register(self, skill: SkillDefinition) -> SkillDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.skills.get(skill.key, skill.version) is not None:
                raise ResourceConflict(f"skill version already exists: {skill.key}@{skill.version}")
            await unit_of_work.skills.add(skill)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="skill",
                    aggregate_id=skill.id,
                    event_type="skill.registered",
                    payload={
                        "key": skill.key,
                        "version": skill.version,
                        "content_digest": skill.content_digest,
                    },
                )
            )
            await unit_of_work.commit()
        return skill

    async def get(self, key: str, version: int | None = None) -> SkillDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            skill = await unit_of_work.skills.get(key, version)
        if skill is None:
            suffix = f"@{version}" if version is not None else ""
            raise ResourceNotFound(f"skill not found: {key}{suffix}")
        return skill

    async def list_latest(self) -> list[SkillDefinition]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.skills.list_latest()
