"""In-memory application adapters used by tests."""

from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from uuid import UUID

from jb_orchestrator.domain import DomainEvent, Project, Run, UserRequest


@dataclass
class MemoryStore:
    projects: dict[UUID, Project] = field(default_factory=dict)
    requests: dict[UUID, UserRequest] = field(default_factory=dict)
    runs: dict[UUID, Run] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)


class MemoryProjectRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, project: Project) -> None:
        self._store.projects[project.id] = project

    async def get(self, project_id: UUID) -> Project | None:
        return self._store.projects.get(project_id)

    async def get_by_key(self, key: str) -> Project | None:
        return next(
            (project for project in self._store.projects.values() if project.key == key), None
        )


class MemoryUserRequestRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request

    async def get(self, request_id: UUID) -> UserRequest | None:
        return self._store.requests.get(request_id)

    async def save(self, request: UserRequest) -> None:
        self._store.requests[request.id] = request


class MemoryRunRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def add(self, run: Run) -> None:
        self._store.runs[run.id] = run

    async def get(self, run_id: UUID) -> Run | None:
        return self._store.runs.get(run_id)

    async def save(self, run: Run) -> None:
        self._store.runs[run.id] = run


class MemoryEventRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def append(self, event: DomainEvent) -> None:
        self._store.events.append(event)


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore) -> None:
        self.projects = MemoryProjectRepository(store)
        self.requests = MemoryUserRequestRepository(store)
        self.runs = MemoryRunRepository(store)
        self.events = MemoryEventRepository(store)
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True
