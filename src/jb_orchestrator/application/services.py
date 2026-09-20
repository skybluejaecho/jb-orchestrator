"""Orchestration application use cases."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from jb_orchestrator.application.budget_services import release_run_reservations
from jb_orchestrator.application.commands import CreateUserRequest, RegisterProject
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.execution_lifecycle import synchronize_execution_lifecycle
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent, Project, ProjectStatus, Run, RunStatus, UserRequest
from jb_orchestrator.workflows import WorkflowEngine


@dataclass(frozen=True, slots=True)
class CreatedRequest:
    """Aggregates created atomically for an accepted user request."""

    request: UserRequest
    run: Run


class OrchestrationService:
    """Coordinates domain rules and persistence transactions."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        engine: WorkflowEngine | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._engine = engine or WorkflowEngine()

    async def register_project(self, command: RegisterProject) -> Project:
        project = Project(
            key=command.key,
            name=command.name,
            repository_url=command.repository_url,
            default_branch=command.default_branch,
        )

        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get_by_key(project.key) is not None:
                raise ResourceConflict(f"project key already exists: {project.key}")
            await unit_of_work.projects.add(project)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="project",
                    aggregate_id=project.id,
                    event_type="project.registered",
                    payload={"key": project.key},
                )
            )
            await unit_of_work.commit()

        return project

    async def get_project(self, project_id: UUID) -> Project:
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(project_id)
        if project is None:
            raise ResourceNotFound(f"project not found: {project_id}")
        return project

    async def create_request(self, command: CreateUserRequest) -> CreatedRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(command.project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {command.project_id}")
            if project.status is not ProjectStatus.ACTIVE:
                raise ResourceConflict(f"project is not active: {command.project_id}")

            request = UserRequest(
                project_id=project.id,
                prompt=command.prompt,
                title=command.title,
            )
            request.activate()
            run = Run(request_id=request.id)
            await unit_of_work.requests.add(request)
            await unit_of_work.runs.add(run)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="request",
                    aggregate_id=request.id,
                    event_type="request.created",
                    payload={"project_id": str(project.id), "run_id": str(run.id)},
                )
            )
            await unit_of_work.commit()

        return CreatedRequest(request=request, run=run)

    async def get_request(self, request_id: UUID) -> UserRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            request = await unit_of_work.requests.get(request_id)
        if request is None:
            raise ResourceNotFound(f"request not found: {request_id}")
        return request

    async def get_run(self, run_id: UUID) -> Run:
        async with self._unit_of_work_factory() as unit_of_work:
            run = await unit_of_work.runs.get(run_id)
        if run is None:
            raise ResourceNotFound(f"run not found: {run_id}")
        return run

    async def approve_run(self, run_id: UUID) -> Run:
        async with self._unit_of_work_factory() as unit_of_work:
            run = await unit_of_work.runs.get_for_update(run_id)
            if run is None:
                raise ResourceNotFound(f"run not found: {run_id}")
            if await unit_of_work.workflow_executions.get_by_run(run_id) is not None:
                raise ResourceConflict("workflow approvals must resolve a specific approval node")
            run.transition_to(RunStatus.READY)
            await unit_of_work.runs.save(run)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="run",
                    aggregate_id=run.id,
                    event_type="run.approved",
                    payload={"status": run.status.value},
                )
            )
            await unit_of_work.commit()
        return run

    async def cancel_run(self, run_id: UUID) -> Run:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await unit_of_work.workflow_executions.get_by_run_for_update(run_id)
            if execution is not None:
                if execution.is_terminal:
                    raise ResourceConflict(f"terminal run cannot be cancelled: {run_id}")
                self._engine.cancel(execution)
                await release_run_reservations(unit_of_work, run_id, reason="run_cancelled")
                await unit_of_work.workflow_executions.save(execution)
                await unit_of_work.events.append(
                    DomainEvent(
                        aggregate_type="workflow_execution",
                        aggregate_id=execution.id,
                        event_type="workflow.cancelled",
                        payload={"status": execution.status.value, "source": "run"},
                    )
                )
                await synchronize_execution_lifecycle(unit_of_work, execution)
                run = await unit_of_work.runs.get(run_id)
                if run is None:
                    raise ResourceNotFound(f"run not found: {run_id}")
                await unit_of_work.commit()
                return run

            run = await unit_of_work.runs.get_for_update(run_id)
            if run is None:
                raise ResourceNotFound(f"run not found: {run_id}")
            request = await unit_of_work.requests.get_for_update(run.request_id)
            if request is None:
                raise ResourceNotFound(f"request not found: {run.request_id}")
            await release_run_reservations(unit_of_work, run.id, reason="run_cancelled")
            run.transition_to(RunStatus.CANCELLED)
            request.cancel()
            await unit_of_work.runs.save(run)
            await unit_of_work.requests.save(request)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="run",
                    aggregate_id=run.id,
                    event_type="run.cancelled",
                    payload={"request_id": str(request.id)},
                )
            )
            await unit_of_work.commit()
        return run
