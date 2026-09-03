"""SQLAlchemy transaction boundary."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jb_orchestrator.infrastructure.database.artifact_repositories import (
    SqlAlchemyTaskArtifactRepository,
)
from jb_orchestrator.infrastructure.database.budget_repositories import (
    SqlAlchemyBudgetAccountRepository,
    SqlAlchemyBudgetReservationRepository,
    SqlAlchemyUsageRecordRepository,
)
from jb_orchestrator.infrastructure.database.external_execution_repositories import (
    SqlAlchemyExternalExecutionRepository,
)
from jb_orchestrator.infrastructure.database.model_repositories import (
    SqlAlchemyModelProfileRepository,
)
from jb_orchestrator.infrastructure.database.repositories import (
    SqlAlchemyEventRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyRunRepository,
    SqlAlchemyUserRequestRepository,
)
from jb_orchestrator.infrastructure.database.skill_repositories import SqlAlchemySkillRepository
from jb_orchestrator.infrastructure.database.workflow_repositories import (
    SqlAlchemyWorkflowDefinitionRepository,
    SqlAlchemyWorkflowExecutionRepository,
)


class SqlAlchemyUnitOfWork:
    """Keep all aggregate changes for a use case in one database transaction."""

    projects: SqlAlchemyProjectRepository
    requests: SqlAlchemyUserRequestRepository
    runs: SqlAlchemyRunRepository
    events: SqlAlchemyEventRepository
    artifacts: SqlAlchemyTaskArtifactRepository
    skills: SqlAlchemySkillRepository
    model_profiles: SqlAlchemyModelProfileRepository
    budget_accounts: SqlAlchemyBudgetAccountRepository
    budget_reservations: SqlAlchemyBudgetReservationRepository
    usage_records: SqlAlchemyUsageRecordRepository
    external_executions: SqlAlchemyExternalExecutionRepository
    workflow_definitions: SqlAlchemyWorkflowDefinitionRepository
    workflow_executions: SqlAlchemyWorkflowExecutionRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.projects = SqlAlchemyProjectRepository(self._session)
        self.requests = SqlAlchemyUserRequestRepository(self._session)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.events = SqlAlchemyEventRepository(self._session)
        self.artifacts = SqlAlchemyTaskArtifactRepository(self._session)
        self.skills = SqlAlchemySkillRepository(self._session)
        self.model_profiles = SqlAlchemyModelProfileRepository(self._session)
        self.budget_accounts = SqlAlchemyBudgetAccountRepository(self._session)
        self.budget_reservations = SqlAlchemyBudgetReservationRepository(self._session)
        self.usage_records = SqlAlchemyUsageRecordRepository(self._session)
        self.external_executions = SqlAlchemyExternalExecutionRepository(self._session)
        self.workflow_definitions = SqlAlchemyWorkflowDefinitionRepository(self._session)
        self.workflow_executions = SqlAlchemyWorkflowExecutionRepository(self._session)
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
