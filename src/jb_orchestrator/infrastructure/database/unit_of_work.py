"""SQLAlchemy transaction boundary."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jb_orchestrator.infrastructure.database.repositories import (
    SqlAlchemyEventRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyRunRepository,
    SqlAlchemyUserRequestRepository,
)


class SqlAlchemyUnitOfWork:
    """Keep all aggregate changes for a use case in one database transaction."""

    projects: SqlAlchemyProjectRepository
    requests: SqlAlchemyUserRequestRepository
    runs: SqlAlchemyRunRepository
    events: SqlAlchemyEventRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.projects = SqlAlchemyProjectRepository(self._session)
        self.requests = SqlAlchemyUserRequestRepository(self._session)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.events = SqlAlchemyEventRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work has not been entered")
        return self._session
