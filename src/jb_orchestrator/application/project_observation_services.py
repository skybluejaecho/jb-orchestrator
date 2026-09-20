"""Project-scoped read models and durable event observation."""

from collections.abc import Callable, Sequence
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import (
    DomainEvent,
    Project,
    ProjectStatus,
    RequestStatus,
    Run,
    RunStatus,
    UserRequest,
)
from jb_orchestrator.workflows import WorkflowExecution, WorkflowStatus


class ProjectObservationService:
    """Expose one project's durable state without client-side joins."""

    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def list_projects(
        self, *, status: ProjectStatus | None = None, limit: int = 100
    ) -> list[Project]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.projects.list(status=status, limit=limit)

    async def list_requests(
        self,
        project_id: UUID,
        *,
        status: RequestStatus | None = None,
        limit: int = 100,
    ) -> list[UserRequest]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._require_project(unit_of_work, project_id)
            return await unit_of_work.requests.list_by_project(
                project_id, status=status, limit=limit
            )

    async def list_runs(
        self,
        request_id: UUID,
        *,
        status: RunStatus | None = None,
        limit: int = 100,
    ) -> list[Run]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.requests.get(request_id) is None:
                raise ResourceNotFound(f"request not found: {request_id}")
            return await unit_of_work.runs.list_by_request(request_id, status=status, limit=limit)

    async def list_workflow_executions(
        self,
        project_id: UUID,
        *,
        status: WorkflowStatus | None = None,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._require_project(unit_of_work, project_id)
            return await unit_of_work.workflow_executions.list_by_project(
                project_id, status=status, limit=limit
            )

    async def list_events(
        self,
        project_id: UUID,
        *,
        after_event_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[DomainEvent]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._require_project(unit_of_work, project_id)
            after = None
            if after_event_id is not None:
                after = await unit_of_work.events.get(after_event_id)
                if after is None:
                    raise ResourceNotFound(f"event cursor not found: {after_event_id}")
            return await unit_of_work.events.list_project_after(
                project_id=project_id,
                after=after,
                limit=limit,
            )

    @staticmethod
    async def _require_project(unit_of_work: UnitOfWork, project_id: UUID) -> None:
        if await unit_of_work.projects.get(project_id) is None:
            raise ResourceNotFound(f"project not found: {project_id}")
