"""Phase-pack catalog use cases."""

from collections.abc import Callable

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.phase_packs import PhasePackDefinition, check_output_contract_schema


class PhasePackCatalogService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def register(self, phase_pack: PhasePackDefinition) -> PhasePackDefinition:
        check_output_contract_schema(phase_pack.output_contract)
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.phase_packs.get(phase_pack.key, phase_pack.version) is not None:
                raise ResourceConflict(
                    f"phase pack version already exists: {phase_pack.key}@{phase_pack.version}"
                )
            for reference in phase_pack.skills:
                if await unit_of_work.skills.get(reference.key, reference.version) is None:
                    raise ResourceNotFound(f"skill not found: {reference.key}@{reference.version}")
            await unit_of_work.phase_packs.add(phase_pack)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="phase_pack",
                    aggregate_id=phase_pack.id,
                    event_type="phase_pack.registered",
                    payload={"key": phase_pack.key, "version": phase_pack.version},
                )
            )
            await unit_of_work.commit()
        return phase_pack

    async def get(self, key: str, version: int | None = None) -> PhasePackDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            phase_pack = await unit_of_work.phase_packs.get(key, version)
        if phase_pack is None:
            suffix = f"@{version}" if version is not None else ""
            raise ResourceNotFound(f"phase pack not found: {key}{suffix}")
        return phase_pack

    async def list_latest(self) -> list[PhasePackDefinition]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.phase_packs.list_latest()
