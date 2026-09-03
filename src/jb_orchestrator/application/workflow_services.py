"""Transactional use cases for durable workflow execution."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from jb_orchestrator.application.budget_services import release_run_reservations
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    NodeModelSelection,
)
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import (
    NodeOutcome,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowExecution,
    WorkflowRequestContext,
    WorkflowSnapshot,
)


class WorkflowService:
    """Apply engine transitions and persist each result atomically with its event."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        engine: WorkflowEngine | None = None,
        model_router: DeterministicModelRouter | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._engine = engine or WorkflowEngine()
        self._model_router = model_router or DeterministicModelRouter()

    async def register_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            stored = await unit_of_work.workflow_definitions.get(definition.key, definition.version)
            if stored is not None:
                raise ResourceConflict(
                    f"workflow definition already exists: {definition.key}@{definition.version}"
                )
            await self._resolve_skills(unit_of_work, definition)
            await unit_of_work.workflow_definitions.add(definition)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="workflow_definition",
                    aggregate_id=definition.id,
                    event_type="workflow.definition_registered",
                    payload={"key": definition.key, "version": definition.version},
                )
            )
            await unit_of_work.commit()
        return definition

    async def get_definition(self, key: str, version: int | None = None) -> WorkflowDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            definition = await unit_of_work.workflow_definitions.get(key, version)
        if definition is None:
            suffix = f"@{version}" if version is not None else ""
            raise ResourceNotFound(f"workflow definition not found: {key}{suffix}")
        return definition

    async def list_latest_definitions(self) -> list[WorkflowDefinition]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflow_definitions.list_latest()

    async def start(
        self, run_id: UUID, definition_key: str, version: int | None = None
    ) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            run = await unit_of_work.runs.get(run_id)
            if run is None:
                raise ResourceNotFound(f"run not found: {run_id}")
            request = await unit_of_work.requests.get(run.request_id)
            if request is None:
                raise ResourceNotFound(f"request not found: {run.request_id}")
            project = await unit_of_work.projects.get(request.project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {request.project_id}")
            if await unit_of_work.workflow_executions.get_by_run(run_id) is not None:
                raise ResourceConflict(f"workflow execution already exists for run: {run_id}")
            definition = await unit_of_work.workflow_definitions.get(definition_key, version)
            if definition is None:
                suffix = f"@{version}" if version is not None else ""
                raise ResourceNotFound(f"workflow definition not found: {definition_key}{suffix}")

            skills = await self._resolve_skills(unit_of_work, definition)
            model_selections = await self._route_models(unit_of_work, definition)

            execution = WorkflowExecution.create(
                WorkflowSnapshot.from_definition(
                    definition,
                    run_id=run_id,
                    request_context=WorkflowRequestContext(
                        request_id=request.id,
                        project_id=project.id,
                        project_key=project.key,
                        project_name=project.name,
                        repository_url=project.repository_url,
                        default_branch=project.default_branch,
                        prompt=request.prompt,
                        title=request.title,
                    ),
                    skills=skills,
                    model_selections=model_selections,
                )
            )
            self._engine.start(execution)
            await unit_of_work.workflow_executions.add(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.started",
                model_selections=[
                    {
                        "node_key": value.node_key,
                        "profile_key": value.selection.profile.key,
                        "profile_version": value.selection.profile.version,
                        "policy_version": value.selection.policy_version,
                        "estimated_cost_usd": str(value.selection.estimated_cost_usd),
                    }
                    for value in model_selections
                ],
            )
            await unit_of_work.commit()
        return execution

    async def get(self, execution_id: UUID) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await unit_of_work.workflow_executions.get(execution_id)
        if execution is None:
            raise ResourceNotFound(f"workflow execution not found: {execution_id}")
        return execution

    async def get_by_run(self, run_id: UUID) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await unit_of_work.workflow_executions.get_by_run(run_id)
        if execution is None:
            raise ResourceNotFound(f"workflow execution not found for run: {run_id}")
        return execution

    async def begin_task(self, execution_id: UUID, node_key: str) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id)
            self._engine.begin_task(execution, node_key)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work, execution, "workflow.node_started", node_key=node_key
            )
            await unit_of_work.commit()
        return execution

    async def complete_task(
        self,
        execution_id: UUID,
        node_key: str,
        outcome: NodeOutcome,
        output: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id)
            visit_count = execution.nodes[node_key].visit_count
            self._engine.complete_task(execution, node_key, outcome, output=output)
            artifact = TaskArtifact(
                execution_id=execution.id,
                producer_node_key=node_key,
                visit_count=visit_count,
                outcome=outcome,
                content=output or {},
            )
            await unit_of_work.artifacts.add(artifact)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.node_completed",
                node_key=node_key,
                outcome=outcome.value,
                artifact_id=str(artifact.id),
            )
            await unit_of_work.commit()
        return execution

    async def list_artifacts(self, execution_id: UUID) -> list[TaskArtifact]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._get_execution(unit_of_work, execution_id)
            return await unit_of_work.artifacts.list_for_execution(execution_id)

    async def fail_task(self, execution_id: UUID, node_key: str, reason: str) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id)
            self._engine.fail_task(execution, node_key, reason)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.node_failed",
                node_key=node_key,
                reason=reason,
            )
            await unit_of_work.commit()
        return execution

    async def resolve_approval(
        self, execution_id: UUID, node_key: str, *, approved: bool
    ) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id)
            self._engine.resolve_approval(execution, node_key, approved=approved)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.approval_resolved",
                node_key=node_key,
                approved=approved,
            )
            await unit_of_work.commit()
        return execution

    async def cancel(self, execution_id: UUID) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id)
            self._engine.cancel(execution)
            await release_run_reservations(
                unit_of_work,
                execution.snapshot.run_id,
                reason="workflow_cancelled",
            )
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(unit_of_work, execution, "workflow.cancelled")
            await unit_of_work.commit()
        return execution

    @staticmethod
    async def _get_execution(unit_of_work: UnitOfWork, execution_id: UUID) -> WorkflowExecution:
        execution = await unit_of_work.workflow_executions.get(execution_id)
        if execution is None:
            raise ResourceNotFound(f"workflow execution not found: {execution_id}")
        return execution

    @staticmethod
    async def _append_event(
        unit_of_work: UnitOfWork,
        execution: WorkflowExecution,
        event_type: str,
        **payload: Any,
    ) -> None:
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="workflow_execution",
                aggregate_id=execution.id,
                event_type=event_type,
                payload={"status": execution.status.value, **payload},
            )
        )

    @staticmethod
    async def _resolve_skills(
        unit_of_work: UnitOfWork, definition: WorkflowDefinition
    ) -> tuple[SkillDefinition, ...]:
        references = {reference for node in definition.nodes for reference in node.skills}
        resolved: list[SkillDefinition] = []
        for reference in sorted(references, key=lambda item: (item.key, item.version)):
            skill = await unit_of_work.skills.get(reference.key, reference.version)
            if skill is None:
                raise ResourceNotFound(f"skill not found: {reference.key}@{reference.version}")
            resolved.append(skill)
        return tuple(resolved)

    async def _route_models(
        self, unit_of_work: UnitOfWork, definition: WorkflowDefinition
    ) -> tuple[NodeModelSelection, ...]:
        routed_nodes = [node for node in definition.nodes if node.model_routing is not None]
        if not routed_nodes:
            return ()
        profiles = await unit_of_work.model_profiles.list_latest()
        return tuple(
            NodeModelSelection(
                node_key=node.key,
                selection=self._model_router.route(
                    node.model_routing,
                    profiles,
                    executor_key=node.executor_key or "default",
                ),
            )
            for node in routed_nodes
            if node.model_routing is not None
        )
