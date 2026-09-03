"""Transactional use cases for durable workflow execution."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from jb_orchestrator.application.budget_services import release_run_reservations
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.execution_lifecycle import synchronize_execution_lifecycle
from jb_orchestrator.application.output_contracts import enforce_output_contract
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.domain import DomainEvent, Project, Run, UserRequest
from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    NodeModelSelection,
)
from jb_orchestrator.phase_packs import PhasePackDefinition
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import (
    NodeOutcome,
    WorkflowDefinition,
    WorkflowDefinitionError,
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
            phase_packs = await self._resolve_phase_packs(unit_of_work, definition)
            await self._resolve_skills(unit_of_work, definition, phase_packs)
            self._validate_phase_inputs(definition, phase_packs)
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
            definition = await unit_of_work.workflow_definitions.get(definition_key, version)
            if definition is None:
                suffix = f"@{version}" if version is not None else ""
                raise ResourceNotFound(f"workflow definition not found: {definition_key}{suffix}")

            execution = await self.create_execution(
                unit_of_work,
                run=run,
                request=request,
                project=project,
                definition=definition,
                selection_source="explicit",
            )
            await unit_of_work.commit()
        return execution

    async def create_execution(
        self,
        unit_of_work: UnitOfWork,
        *,
        run: Run,
        request: UserRequest,
        project: Project,
        definition: WorkflowDefinition,
        selection_source: str,
    ) -> WorkflowExecution:
        """Create and start an execution inside the caller's transaction."""

        if await unit_of_work.workflow_executions.get_by_run(run.id) is not None:
            raise ResourceConflict(f"workflow execution already exists for run: {run.id}")
        phase_packs = await self._resolve_phase_packs(unit_of_work, definition)
        skills = await self._resolve_skills(unit_of_work, definition, phase_packs)
        model_selections = await self._route_models(unit_of_work, definition)
        execution = WorkflowExecution.create(
            WorkflowSnapshot.from_definition(
                definition,
                run_id=run.id,
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
                phase_packs=phase_packs,
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
            selection_source=selection_source,
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
        await synchronize_execution_lifecycle(unit_of_work, execution)
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
            execution = await self._get_execution(unit_of_work, execution_id, for_update=True)
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
            execution = await self._get_execution(unit_of_work, execution_id, for_update=True)
            visit_count = execution.nodes[node_key].visit_count
            definition = execution.snapshot.node(node_key)
            phase_pack = (
                execution.snapshot.phase_pack(definition.phase_pack)
                if definition.phase_pack is not None
                else None
            )
            decision = enforce_output_contract(phase_pack, outcome, output or {})
            effective_output = decision.output if decision.rejected else output
            self._engine.complete_task(
                execution,
                node_key,
                decision.outcome,
                output=effective_output,
            )
            artifact = TaskArtifact(
                execution_id=execution.id,
                producer_node_key=node_key,
                visit_count=visit_count,
                outcome=decision.outcome,
                content=decision.output,
            )
            await unit_of_work.artifacts.add(artifact)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.node_completed",
                node_key=node_key,
                outcome=decision.outcome.value,
                artifact_id=str(artifact.id),
                output_contract_rejected=decision.rejected,
            )
            await synchronize_execution_lifecycle(unit_of_work, execution)
            await unit_of_work.commit()
        return execution

    async def list_artifacts(self, execution_id: UUID) -> list[TaskArtifact]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._get_execution(unit_of_work, execution_id)
            return await unit_of_work.artifacts.list_for_execution(execution_id)

    async def fail_task(self, execution_id: UUID, node_key: str, reason: str) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id, for_update=True)
            self._engine.fail_task(execution, node_key, reason)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.node_failed",
                node_key=node_key,
                reason=reason,
            )
            await synchronize_execution_lifecycle(unit_of_work, execution)
            await unit_of_work.commit()
        return execution

    async def resolve_approval(
        self, execution_id: UUID, node_key: str, *, approved: bool
    ) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id, for_update=True)
            self._engine.resolve_approval(execution, node_key, approved=approved)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "workflow.approval_resolved",
                node_key=node_key,
                approved=approved,
            )
            await synchronize_execution_lifecycle(unit_of_work, execution)
            await unit_of_work.commit()
        return execution

    async def cancel(self, execution_id: UUID) -> WorkflowExecution:
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, execution_id, for_update=True)
            self._engine.cancel(execution)
            await release_run_reservations(
                unit_of_work,
                execution.snapshot.run_id,
                reason="workflow_cancelled",
            )
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(unit_of_work, execution, "workflow.cancelled")
            await synchronize_execution_lifecycle(unit_of_work, execution)
            await unit_of_work.commit()
        return execution

    @staticmethod
    async def _get_execution(
        unit_of_work: UnitOfWork,
        execution_id: UUID,
        *,
        for_update: bool = False,
    ) -> WorkflowExecution:
        execution = (
            await unit_of_work.workflow_executions.get_for_update(execution_id)
            if for_update
            else await unit_of_work.workflow_executions.get(execution_id)
        )
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
        unit_of_work: UnitOfWork,
        definition: WorkflowDefinition,
        phase_packs: tuple[PhasePackDefinition, ...] = (),
    ) -> tuple[SkillDefinition, ...]:
        references = {reference for node in definition.nodes for reference in node.skills}
        references.update(reference for value in phase_packs for reference in value.skills)
        resolved: list[SkillDefinition] = []
        for reference in sorted(references, key=lambda item: (item.key, item.version)):
            skill = await unit_of_work.skills.get(reference.key, reference.version)
            if skill is None:
                raise ResourceNotFound(f"skill not found: {reference.key}@{reference.version}")
            resolved.append(skill)
        return tuple(resolved)

    @staticmethod
    async def _resolve_phase_packs(
        unit_of_work: UnitOfWork, definition: WorkflowDefinition
    ) -> tuple[PhasePackDefinition, ...]:
        references = {node.phase_pack for node in definition.nodes if node.phase_pack is not None}
        resolved: list[PhasePackDefinition] = []
        for reference in sorted(references, key=lambda item: (item.key, item.version)):
            phase_pack = await unit_of_work.phase_packs.get(reference.key, reference.version)
            if phase_pack is None:
                raise ResourceNotFound(f"phase pack not found: {reference.key}@{reference.version}")
            resolved.append(phase_pack)
        return tuple(resolved)

    @staticmethod
    def _validate_phase_inputs(
        definition: WorkflowDefinition, phase_packs: tuple[PhasePackDefinition, ...]
    ) -> None:
        by_reference = {value.reference: value for value in phase_packs}
        for node in definition.nodes:
            if node.phase_pack is None:
                continue
            phase_pack = by_reference[node.phase_pack]
            declared = {value.key: value for value in phase_pack.inputs}
            mapped = {value.input_key for value in node.input_mappings}
            if not mapped <= set(declared):
                raise WorkflowDefinitionError(
                    f"node {node.key} maps an undeclared input from {phase_pack.key}"
                )
            missing = sorted(
                key for key, value in declared.items() if value.required and key not in mapped
            )
            if missing:
                raise WorkflowDefinitionError(
                    f"node {node.key} is missing required phase inputs: {', '.join(missing)}"
                )

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
