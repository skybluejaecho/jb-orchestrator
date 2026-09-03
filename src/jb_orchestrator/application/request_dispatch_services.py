"""Project workflow binding and one-call request dispatch use cases."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.application.workflow_services import WorkflowService
from jb_orchestrator.domain import DomainEvent, ProjectStatus, Run, UserRequest
from jb_orchestrator.workflows import ProjectWorkflowBinding, WorkflowExecution


@dataclass(frozen=True, slots=True)
class DispatchedRequest:
    """Aggregates created atomically from one user prompt."""

    request: UserRequest
    run: Run
    workflow: WorkflowExecution


class RequestDispatchService:
    """Select a project's pinned workflow and create all execution state atomically."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        workflow_service: WorkflowService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._workflow_service = workflow_service or WorkflowService(unit_of_work_factory)

    async def configure_binding(
        self, project_id: UUID, definition_key: str, definition_version: int
    ) -> ProjectWorkflowBinding:
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            definition = await unit_of_work.workflow_definitions.get(
                definition_key, definition_version
            )
            if definition is None:
                raise ResourceNotFound(
                    f"workflow definition not found: {definition_key}@{definition_version}"
                )
            binding = await unit_of_work.project_workflow_bindings.get_by_project(
                project_id, for_update=True
            )
            changed_at = datetime.now(UTC)
            if binding is None:
                binding = ProjectWorkflowBinding(
                    project_id=project_id,
                    definition_id=definition.id,
                    definition_key=definition.key,
                    definition_version=definition.version,
                    created_at=changed_at,
                    updated_at=changed_at,
                )
            else:
                binding.definition_id = definition.id
                binding.definition_key = definition.key
                binding.definition_version = definition.version
                binding.updated_at = changed_at
            await unit_of_work.project_workflow_bindings.save(binding)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="project",
                    aggregate_id=project_id,
                    event_type="project.workflow_bound",
                    payload={
                        "definition_id": str(definition.id),
                        "definition_key": definition.key,
                        "definition_version": definition.version,
                    },
                )
            )
            await unit_of_work.commit()
        return binding

    async def get_binding(self, project_id: UUID) -> ProjectWorkflowBinding:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            binding = await unit_of_work.project_workflow_bindings.get_by_project(project_id)
        if binding is None:
            raise ResourceNotFound(f"project workflow binding not found: {project_id}")
        return binding

    async def dispatch(
        self, project_id: UUID, prompt: str, title: str | None = None
    ) -> DispatchedRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            if project.status is not ProjectStatus.ACTIVE:
                raise ResourceConflict(f"project is not active: {project_id}")
            binding = await unit_of_work.project_workflow_bindings.get_by_project(
                project_id, for_update=True
            )
            if binding is None:
                raise ResourceConflict(f"project workflow binding is not configured: {project_id}")
            definition = await unit_of_work.workflow_definitions.get(
                binding.definition_key, binding.definition_version
            )
            if definition is None or definition.id != binding.definition_id:
                raise ResourceConflict(f"bound workflow definition is unavailable: {project_id}")

            request = UserRequest(project_id=project.id, prompt=prompt, title=title)
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
            workflow = await self._workflow_service.create_execution(
                unit_of_work,
                run=run,
                request=request,
                project=project,
                definition=definition,
                selection_source="project_binding",
            )
            await unit_of_work.commit()
        return DispatchedRequest(request=request, run=run, workflow=workflow)
