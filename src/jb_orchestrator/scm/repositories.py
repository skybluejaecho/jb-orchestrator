"""Persistence port for durable SCM publication requests."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.scm.models import (
    ScmPublication,
    ScmPublicationAttempt,
    ScmPublicationClaim,
)


class ScmPublicationRepository(Protocol):
    async def try_add(self, publication: ScmPublication) -> bool: ...

    async def get(
        self, publication_id: UUID, *, for_update: bool = False
    ) -> ScmPublication | None: ...

    async def get_by_idempotency_key(
        self, external_execution_id: UUID, idempotency_key: str
    ) -> ScmPublication | None: ...

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[ScmPublication]: ...

    async def claim_next(
        self, *, worker_id: str, provider_key: str, workspace_scope: str, lease_seconds: int
    ) -> ScmPublicationClaim | None: ...

    async def save(self, publication: ScmPublication) -> None: ...


class ScmPublicationAttemptRepository(Protocol):
    async def add(self, attempt: ScmPublicationAttempt) -> None: ...

    async def get(
        self, publication_id: UUID, attempt_number: int, *, for_update: bool = False
    ) -> ScmPublicationAttempt | None: ...

    async def list_for_publication(
        self, publication_id: UUID, *, limit: int = 100
    ) -> list[ScmPublicationAttempt]: ...

    async def save(self, attempt: ScmPublicationAttempt) -> None: ...
