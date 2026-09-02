"""Persistence ports required by application use cases."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.domain.events import DomainEvent
from jb_orchestrator.domain.projects import Project
from jb_orchestrator.domain.requests import UserRequest
from jb_orchestrator.domain.runs import Run


class ProjectRepository(Protocol):
    """Project persistence contract."""

    async def add(self, project: Project) -> None: ...

    async def get(self, project_id: UUID) -> Project | None: ...

    async def get_by_key(self, key: str) -> Project | None: ...


class UserRequestRepository(Protocol):
    """User request persistence contract."""

    async def add(self, request: UserRequest) -> None: ...

    async def get(self, request_id: UUID) -> UserRequest | None: ...

    async def save(self, request: UserRequest) -> None: ...


class RunRepository(Protocol):
    """Run persistence contract."""

    async def add(self, run: Run) -> None: ...

    async def get(self, run_id: UUID) -> Run | None: ...

    async def save(self, run: Run) -> None: ...


class EventRepository(Protocol):
    """Append-only domain event persistence contract."""

    async def append(self, event: DomainEvent) -> None: ...
