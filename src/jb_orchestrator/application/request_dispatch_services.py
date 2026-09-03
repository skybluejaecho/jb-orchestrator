"""Project workflow binding and one-call request dispatch use cases."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from jb_orchestrator.application.commands import DispatchProjectRequest
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.application.workflow_services import WorkflowService
from jb_orchestrator.domain import (
    DomainEvent,
    ProjectStatus,
    RequestDispatchReceipt,
    RequestOrigin,
    Run,
    UserRequest,
)
from jb_orchestrator.workflows import ProjectWorkflowBinding, WorkflowExecution


@dataclass(frozen=True, slots=True)
class DispatchedRequest:
    """Aggregates created atomically from one user prompt."""

    request: UserRequest
    run: Run
    workflow: WorkflowExecution
    replayed: bool = False


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

    async def dispatch(self, command: DispatchProjectRequest) -> DispatchedRequest:
        normalized_prompt = command.prompt.strip()
        normalized_title = command.title.strip() if command.title else None
        normalized_title = normalized_title or None
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(command.project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {command.project_id}")
            receipt = RequestDispatchReceipt(
                project_id=command.project_id,
                ingress_key=command.origin.ingress_key,
                idempotency_key=command.idempotency_key,
                payload_digest=self._payload_digest(
                    normalized_prompt, normalized_title, command.origin
                ),
            )
            if not await unit_of_work.request_dispatch_receipts.try_claim(receipt):
                existing = await unit_of_work.request_dispatch_receipts.get(
                    command.project_id,
                    receipt.ingress_key,
                    receipt.idempotency_key,
                    for_update=True,
                )
                if existing is None:
                    raise RuntimeError("claimed dispatch receipt could not be loaded")
                if existing.payload_digest != receipt.payload_digest:
                    raise ResourceConflict(
                        "idempotency key was already used with a different request payload"
                    )
                return await self._replay(unit_of_work, existing)
            if project.status is not ProjectStatus.ACTIVE:
                raise ResourceConflict(f"project is not active: {command.project_id}")
            binding = await unit_of_work.project_workflow_bindings.get_by_project(
                command.project_id, for_update=True
            )
            if binding is None:
                raise ResourceConflict(
                    f"project workflow binding is not configured: {command.project_id}"
                )
            definition = await unit_of_work.workflow_definitions.get(
                binding.definition_key, binding.definition_version
            )
            if definition is None or definition.id != binding.definition_id:
                raise ResourceConflict(
                    f"bound workflow definition is unavailable: {command.project_id}"
                )

            request = UserRequest(
                project_id=project.id,
                prompt=normalized_prompt,
                title=normalized_title,
                origin=command.origin,
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
                    payload={
                        "project_id": str(project.id),
                        "run_id": str(run.id),
                        "origin": {
                            "ingress_key": command.origin.ingress_key,
                            "external_request_id": command.origin.external_request_id,
                            "actor_id": command.origin.actor_id,
                            "conversation_id": command.origin.conversation_id,
                        },
                    },
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
            synchronized_run = await unit_of_work.runs.get(run.id)
            synchronized_request = await unit_of_work.requests.get(request.id)
            if synchronized_run is None or synchronized_request is None:
                raise RuntimeError("dispatched request lifecycle state was not persisted")
            receipt.complete(
                request_id=synchronized_request.id,
                run_id=synchronized_run.id,
                workflow_execution_id=workflow.id,
                at=workflow.updated_at,
            )
            await unit_of_work.request_dispatch_receipts.save(receipt)
            await unit_of_work.commit()
        return DispatchedRequest(
            request=synchronized_request,
            run=synchronized_run,
            workflow=workflow,
        )

    @staticmethod
    def _payload_digest(prompt: str, title: str | None, origin: RequestOrigin) -> str:
        normalized_title = title.strip() if title else None
        payload = json.dumps(
            {
                "prompt": prompt.strip(),
                "title": normalized_title or None,
                "origin": {
                    "ingress_key": origin.ingress_key,
                    "external_request_id": origin.external_request_id,
                    "actor_id": origin.actor_id,
                    "conversation_id": origin.conversation_id,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return f"sha256:{sha256(payload).hexdigest()}"

    @staticmethod
    async def _replay(
        unit_of_work: UnitOfWork, receipt: RequestDispatchReceipt
    ) -> DispatchedRequest:
        request_id = receipt.request_id
        run_id = receipt.run_id
        execution_id = receipt.workflow_execution_id
        if request_id is None or run_id is None or execution_id is None:
            raise ResourceConflict(
                "request dispatch with this idempotency key is still in progress"
            )
        request = await unit_of_work.requests.get(request_id)
        run = await unit_of_work.runs.get(run_id)
        workflow = await unit_of_work.workflow_executions.get(execution_id)
        if request is None or run is None or workflow is None:
            raise ResourceConflict("completed request dispatch result is unavailable")
        return DispatchedRequest(request=request, run=run, workflow=workflow, replayed=True)
