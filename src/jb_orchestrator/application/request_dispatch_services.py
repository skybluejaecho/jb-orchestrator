"""Project workflow binding and one-call request dispatch use cases."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from jb_orchestrator.application.commands import DispatchProjectRequest, NodeSkillAddon
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
from jb_orchestrator.phase_packs import PhasePackDefinition
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import (
    ProjectWorkflowBinding,
    WorkflowDefinition,
    WorkflowExecution,
)


@dataclass(frozen=True, slots=True)
class DispatchedRequest:
    """Aggregates created atomically from one user prompt."""

    request: UserRequest
    run: Run
    workflow: WorkflowExecution
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ProjectWorkflowOptions:
    """Selectable workflows and the optional project-level default."""

    default: ProjectWorkflowBinding | None
    default_workflow: "WorkflowComposition | None"
    workflows: tuple["WorkflowComposition", ...]
    available_skills: tuple[SkillDefinition, ...]


@dataclass(frozen=True, slots=True)
class WorkflowComposition:
    """One workflow plus the exact reusable components it references."""

    definition: WorkflowDefinition
    phase_packs: tuple[PhasePackDefinition, ...]
    skills: tuple[SkillDefinition, ...]

    @property
    def key(self) -> str:
        return self.definition.key

    @property
    def version(self) -> int:
        return self.definition.version


class RequestDispatchService:
    """Select an exact requested or project-default workflow and dispatch atomically."""

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

    async def list_workflow_options(self, project_id: UUID) -> ProjectWorkflowOptions:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            binding = await unit_of_work.project_workflow_bindings.get_by_project(project_id)
            definitions = await unit_of_work.workflow_definitions.list_latest()
            available_skills = tuple(await unit_of_work.skills.list_latest())
            default_workflow = None
            if binding is not None:
                default_definition = await unit_of_work.workflow_definitions.get(
                    binding.definition_key, binding.definition_version
                )
                if default_definition is None or default_definition.id != binding.definition_id:
                    raise ResourceConflict(
                        f"bound workflow definition is unavailable: {project_id}"
                    )
                default_workflow = await self._resolve_composition(
                    unit_of_work, default_definition
                )
            compositions_list: list[WorkflowComposition] = []
            for definition in definitions:
                compositions_list.append(
                    await self._resolve_composition(unit_of_work, definition)
                )
        return ProjectWorkflowOptions(
            default=binding,
            default_workflow=default_workflow,
            workflows=tuple(compositions_list),
            available_skills=available_skills,
        )

    @staticmethod
    async def _resolve_composition(
        unit_of_work: UnitOfWork, definition: WorkflowDefinition
    ) -> WorkflowComposition:
        phase_pack_references = sorted(
            {node.phase_pack for node in definition.nodes if node.phase_pack is not None},
            key=lambda value: (value.key, value.version),
        )
        phase_packs: list[PhasePackDefinition] = []
        for reference in phase_pack_references:
            phase_pack = await unit_of_work.phase_packs.get(reference.key, reference.version)
            if phase_pack is None:
                raise ResourceConflict(
                    "workflow option references an unavailable phase pack: "
                    f"{reference.key}@{reference.version}"
                )
            phase_packs.append(phase_pack)

        skill_references = {
            skill_reference
            for node in definition.nodes
            for skill_reference in node.skills
        }
        skill_references.update(
            skill_reference
            for phase_pack in phase_packs
            for skill_reference in phase_pack.skills
        )
        skills: list[SkillDefinition] = []
        for skill_reference in sorted(
            skill_references, key=lambda value: (value.key, value.version)
        ):
            skill = await unit_of_work.skills.get(skill_reference.key, skill_reference.version)
            if skill is None:
                raise ResourceConflict(
                    "workflow option references an unavailable skill: "
                    f"{skill_reference.key}@{skill_reference.version}"
                )
            skills.append(skill)
        return WorkflowComposition(
            definition=definition,
            phase_packs=tuple(phase_packs),
            skills=tuple(skills),
        )

    async def dispatch(self, command: DispatchProjectRequest) -> DispatchedRequest:
        normalized_prompt = command.prompt.strip()
        normalized_title = command.title.strip() if command.title else None
        normalized_title = normalized_title or None
        definition_key = command.definition_key.strip() if command.definition_key else None
        definition_key = definition_key or None
        if (definition_key is None) != (command.definition_version is None):
            raise ResourceConflict(
                "request workflow override requires definition_key and definition_version"
            )
        normalized_addons = self._normalize_skill_addons(command.skill_addons)
        async with self._unit_of_work_factory() as unit_of_work:
            project = await unit_of_work.projects.get(command.project_id)
            if project is None:
                raise ResourceNotFound(f"project not found: {command.project_id}")
            receipt = RequestDispatchReceipt(
                project_id=command.project_id,
                ingress_key=command.origin.ingress_key,
                idempotency_key=command.idempotency_key,
                payload_digest=self._payload_digest(
                    normalized_prompt,
                    normalized_title,
                    command.origin,
                    definition_key,
                    command.definition_version,
                    normalized_addons,
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
            if definition_key is not None and command.definition_version is not None:
                definition = await unit_of_work.workflow_definitions.get(
                    definition_key, command.definition_version
                )
                if definition is None:
                    raise ResourceNotFound(
                        "workflow definition not found: "
                        f"{definition_key}@{command.definition_version}"
                    )
                selection_source = "request_override"
            else:
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
                selection_source = "project_binding"

            definition = await self._apply_skill_addons(
                unit_of_work, definition, normalized_addons
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
                        "workflow_selection": {
                            "source": selection_source,
                            "definition_key": definition.key,
                            "definition_version": definition.version,
                        },
                        "skill_addons": [
                            {
                                "node_key": addon.node_key,
                                "skills": [
                                    {"key": skill.key, "version": skill.version}
                                    for skill in addon.skills
                                ],
                            }
                            for addon in normalized_addons
                        ],
                    },
                )
            )
            workflow = await self._workflow_service.create_execution(
                unit_of_work,
                run=run,
                request=request,
                project=project,
                definition=definition,
                selection_source=selection_source,
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
    def _payload_digest(
        prompt: str,
        title: str | None,
        origin: RequestOrigin,
        definition_key: str | None = None,
        definition_version: int | None = None,
        skill_addons: tuple[NodeSkillAddon, ...] = (),
    ) -> str:
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
                "workflow": (
                    {
                        "definition_key": definition_key,
                        "definition_version": definition_version,
                    }
                    if definition_key is not None and definition_version is not None
                    else None
                ),
                "skill_addons": [
                    {
                        "node_key": addon.node_key,
                        "skills": [
                            {"key": skill.key, "version": skill.version}
                            for skill in addon.skills
                        ],
                    }
                    for addon in skill_addons
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return f"sha256:{sha256(payload).hexdigest()}"

    @staticmethod
    def _normalize_skill_addons(
        addons: tuple[NodeSkillAddon, ...],
    ) -> tuple[NodeSkillAddon, ...]:
        node_keys = [addon.node_key.strip() for addon in addons]
        if len(node_keys) != len(set(node_keys)):
            raise ResourceConflict("request skill add-on node keys must be unique")
        normalized: list[NodeSkillAddon] = []
        for addon, node_key in zip(addons, node_keys, strict=True):
            if not node_key:
                raise ResourceConflict("request skill add-on node key must not be empty")
            skills = tuple(sorted(set(addon.skills), key=lambda value: (value.key, value.version)))
            if not skills:
                raise ResourceConflict("request skill add-on requires at least one skill")
            normalized.append(NodeSkillAddon(node_key=node_key, skills=skills))
        return tuple(sorted(normalized, key=lambda value: value.node_key))

    @staticmethod
    async def _apply_skill_addons(
        unit_of_work: UnitOfWork,
        definition: WorkflowDefinition,
        addons: tuple[NodeSkillAddon, ...],
    ) -> WorkflowDefinition:
        if not addons:
            return definition
        nodes_by_key = {node.key: node for node in definition.nodes}
        additions_by_node = {addon.node_key: addon.skills for addon in addons}
        for node_key, skills in additions_by_node.items():
            node = nodes_by_key.get(node_key)
            if node is None:
                raise ResourceConflict(f"request skill add-on node not found: {node_key}")
            if node.kind.value != "task":
                raise ResourceConflict(
                    f"request skill add-ons require a task node: {node_key}"
                )
            for skill in skills:
                if await unit_of_work.skills.get(skill.key, skill.version) is None:
                    raise ResourceNotFound(f"skill not found: {skill.key}@{skill.version}")
        return replace(
            definition,
            nodes=tuple(
                replace(
                    node,
                    skills=tuple(
                        sorted(
                            set(node.skills) | set(additions_by_node.get(node.key, ())),
                            key=lambda value: (value.key, value.version),
                        )
                    ),
                )
                if node.key in additions_by_node
                else node
                for node in definition.nodes
            ),
        )

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
