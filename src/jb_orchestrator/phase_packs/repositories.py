"""Persistence port for the phase-pack catalog."""

from typing import Protocol

from jb_orchestrator.phase_packs.models import PhasePackDefinition


class PhasePackRepository(Protocol):
    async def add(self, phase_pack: PhasePackDefinition) -> None: ...

    async def get(self, key: str, version: int | None = None) -> PhasePackDefinition | None: ...

    async def list_latest(self) -> list[PhasePackDefinition]: ...
