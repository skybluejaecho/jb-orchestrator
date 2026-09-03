"""Persistence port for service accounts."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.security.models import ServiceAccount


class ServiceAccountRepository(Protocol):
    async def add(self, account: ServiceAccount) -> None: ...

    async def get(self, account_id: UUID) -> ServiceAccount | None: ...

    async def get_by_key(self, key: str) -> ServiceAccount | None: ...

    async def disable(self, account_id: UUID) -> None: ...
