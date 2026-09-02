"""Versioned model profile catalog use cases."""

from collections.abc import Callable

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.model_routing import ModelProfile


class ModelCatalogService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def register(self, profile: ModelProfile) -> ModelProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.model_profiles.get(profile.key, profile.version) is not None:
                raise ResourceConflict(
                    f"model profile version already exists: {profile.key}@{profile.version}"
                )
            await unit_of_work.model_profiles.add(profile)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="model_profile",
                    aggregate_id=profile.id,
                    event_type="model.registered",
                    payload={
                        "key": profile.key,
                        "version": profile.version,
                        "provider": profile.provider,
                        "model_id": profile.model_id,
                        "tier": profile.tier.value,
                        "enabled": profile.enabled,
                    },
                )
            )
            await unit_of_work.commit()
        return profile

    async def get(self, key: str, version: int | None = None) -> ModelProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            profile = await unit_of_work.model_profiles.get(key, version)
        if profile is None:
            suffix = f"@{version}" if version is not None else ""
            raise ResourceNotFound(f"model profile not found: {key}{suffix}")
        return profile

    async def list_latest(self) -> list[ModelProfile]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.model_profiles.list_latest()
