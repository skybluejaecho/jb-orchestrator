"""Transaction boundary required by orchestration use cases."""

from types import TracebackType
from typing import Protocol, Self

from jb_orchestrator.domain.repositories import (
    EventRepository,
    ProjectRepository,
    RunRepository,
    UserRequestRepository,
)
from jb_orchestrator.workflows.repositories import (
    WorkflowDefinitionRepository,
    WorkflowExecutionRepository,
)


class UnitOfWork(Protocol):
    """Repositories participating in one atomic transaction."""

    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def requests(self) -> UserRequestRepository: ...

    @property
    def runs(self) -> RunRepository: ...

    @property
    def events(self) -> EventRepository: ...

    @property
    def workflow_definitions(self) -> WorkflowDefinitionRepository: ...

    @property
    def workflow_executions(self) -> WorkflowExecutionRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
