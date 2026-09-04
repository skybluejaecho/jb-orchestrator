"""Workflow definition, snapshot, and execution state."""

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.model_routing import (
    ModelRoutingRequest,
    ModelSelection,
    NodeModelSelection,
)
from jb_orchestrator.phase_packs import PhasePackDefinition, PhasePackReference
from jb_orchestrator.skills import SkillDefinition, SkillReference
from jb_orchestrator.workflows.exceptions import WorkflowDefinitionError

NODE_INPUT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
JSON_POINTER_PATTERN = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeKind(StrEnum):
    TASK = "task"
    APPROVAL = "approval"
    FORK = "fork"
    JOIN = "join"
    TERMINAL = "terminal"


class NodeOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    APPROVED = "approved"
    REJECTED = "rejected"


class NodeExecutionStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowRequestContext:
    """Immutable user intent and repository identity pinned for one workflow run."""

    request_id: UUID
    project_id: UUID
    project_key: str
    project_name: str
    repository_url: str
    default_branch: str
    prompt: str
    title: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.project_key,
            self.project_name,
            self.repository_url,
            self.default_branch,
            self.prompt,
        )
        if any(not value.strip() for value in required):
            raise WorkflowDefinitionError("workflow request context fields must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeInputMapping:
    """Bind one phase-pack input name to a producer node's latest artifact."""

    input_key: str
    source_node: str

    def __post_init__(self) -> None:
        if not NODE_INPUT_KEY_PATTERN.fullmatch(self.input_key):
            raise WorkflowDefinitionError("node input mapping key must be lower snake_case")
        if not self.source_node.strip():
            raise WorkflowDefinitionError("node input mapping fields must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeDefinition:
    key: str
    kind: NodeKind
    max_attempts: int = 1
    max_visits: int = 1
    timeout_seconds: int = 600
    terminal_status: WorkflowStatus | None = None
    executor_key: str | None = None
    instructions: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    skills: tuple[SkillReference, ...] = ()
    model_routing: ModelRoutingRequest | None = None
    phase_pack: PhasePackReference | None = None
    input_mappings: tuple[NodeInputMapping, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise WorkflowDefinitionError("node key must not be empty")
        if self.max_attempts < 1:
            raise WorkflowDefinitionError("node max_attempts must be greater than zero")
        if self.max_visits < 1:
            raise WorkflowDefinitionError("node max_visits must be greater than zero")
        if self.timeout_seconds < 1:
            raise WorkflowDefinitionError("node timeout_seconds must be greater than zero")
        if self.kind in {NodeKind.FORK, NodeKind.JOIN} and self.max_visits != 1:
            raise WorkflowDefinitionError("fork and join nodes currently allow only one visit")
        terminal_statuses = {WorkflowStatus.SUCCEEDED, WorkflowStatus.FAILED}
        if self.kind is NodeKind.TERMINAL and self.terminal_status not in terminal_statuses:
            raise WorkflowDefinitionError("terminal node requires succeeded or failed status")
        if self.kind is not NodeKind.TERMINAL and self.terminal_status is not None:
            raise WorkflowDefinitionError("only terminal nodes may define terminal_status")
        if self.executor_key is not None:
            if self.kind is not NodeKind.TASK:
                raise WorkflowDefinitionError("only task nodes may define executor_key")
            if not self.executor_key.strip():
                raise WorkflowDefinitionError("node executor_key must not be empty")
        if self.instructions is not None and not self.instructions.strip():
            raise WorkflowDefinitionError("node instructions must not be empty")
        if self.kind is not NodeKind.TASK and (self.instructions or self.configuration):
            raise WorkflowDefinitionError(
                "only task nodes may define instructions or configuration"
            )
        if self.kind is not NodeKind.TASK and self.skills:
            raise WorkflowDefinitionError("only task nodes may reference skills")
        if self.kind is not NodeKind.TASK and self.model_routing is not None:
            raise WorkflowDefinitionError("only task nodes may define model routing")
        if self.kind is not NodeKind.TASK and self.phase_pack is not None:
            raise WorkflowDefinitionError("only task nodes may reference phase packs")
        if self.kind is not NodeKind.TASK and self.input_mappings:
            raise WorkflowDefinitionError("only task nodes may define input mappings")
        if self.phase_pack is None and self.input_mappings:
            raise WorkflowDefinitionError("node input mappings require a phase pack")
        if len({value.input_key for value in self.input_mappings}) != len(self.input_mappings):
            raise WorkflowDefinitionError("node input mapping keys must be unique")
        if len(set(self.skills)) != len(self.skills):
            raise WorkflowDefinitionError("node skill references must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactCondition:
    """Match one scalar value in a task artifact through an RFC 6901 JSON Pointer."""

    path: str
    equals: str | int | float | bool | None

    def __post_init__(self) -> None:
        if not self.path or len(self.path) > 512 or not JSON_POINTER_PATTERN.fullmatch(self.path):
            raise WorkflowDefinitionError(
                "artifact condition path must be a non-empty JSON Pointer"
            )
        if not isinstance(self.equals, (str, int, float, bool, type(None))) or (
            isinstance(self.equals, float) and not isfinite(self.equals)
        ):
            raise WorkflowDefinitionError("artifact condition value must be a finite JSON scalar")


@dataclass(frozen=True, slots=True, kw_only=True)
class EdgeDefinition:
    source: str
    outcome: NodeOutcome
    target: str
    condition: ArtifactCondition | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowDefinition:
    key: str
    version: int
    entry_node: str
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise WorkflowDefinitionError("workflow key must not be empty")
        if self.version < 1:
            raise WorkflowDefinitionError("workflow version must be greater than zero")

        nodes_by_key = {node.key: node for node in self.nodes}
        if len(nodes_by_key) != len(self.nodes):
            raise WorkflowDefinitionError("workflow node keys must be unique")
        if self.entry_node not in nodes_by_key:
            raise WorkflowDefinitionError("workflow entry node does not exist")

        outgoing: dict[str, set[NodeOutcome]] = {key: set() for key in nodes_by_key}
        edges_by_route: dict[tuple[str, NodeOutcome], list[EdgeDefinition]] = {}
        seen_edges: set[EdgeDefinition] = set()
        adjacency: dict[str, set[str]] = {key: set() for key in nodes_by_key}
        incoming: dict[str, set[str]] = {key: set() for key in nodes_by_key}
        for edge in self.edges:
            if edge.source not in nodes_by_key or edge.target not in nodes_by_key:
                raise WorkflowDefinitionError("workflow edge references an unknown node")
            source_kind = nodes_by_key[edge.source].kind
            if edge.condition is not None and source_kind is not NodeKind.TASK:
                raise WorkflowDefinitionError("only task edges may define artifact conditions")
            if edge in seen_edges:
                raise WorkflowDefinitionError("duplicate workflow edges are not allowed")
            seen_edges.add(edge)
            allowed_outcomes = {
                NodeKind.TASK: {NodeOutcome.SUCCESS, NodeOutcome.FAILURE},
                NodeKind.APPROVAL: {NodeOutcome.APPROVED, NodeOutcome.REJECTED},
                NodeKind.FORK: {NodeOutcome.SUCCESS},
                NodeKind.JOIN: {NodeOutcome.SUCCESS},
                NodeKind.TERMINAL: set(),
            }[source_kind]
            if edge.outcome not in allowed_outcomes:
                raise WorkflowDefinitionError("edge outcome is invalid for its source node")
            outgoing[edge.source].add(edge.outcome)
            edges_by_route.setdefault((edge.source, edge.outcome), []).append(edge)
            adjacency[edge.source].add(edge.target)
            incoming[edge.target].add(edge.source)

        for (route_source, _), route_edges in edges_by_route.items():
            source_kind = nodes_by_key[route_source].kind
            if source_kind is NodeKind.FORK:
                continue
            defaults = [edge for edge in route_edges if edge.condition is None]
            conditional = [edge for edge in route_edges if edge.condition is not None]
            if len(defaults) > 1:
                raise WorkflowDefinitionError("node outcomes may have only one default target")
            if len(route_edges) > 1 and not conditional:
                raise WorkflowDefinitionError("node outcomes may have only one target")
            paths = {edge.condition.path for edge in conditional if edge.condition is not None}
            if len(paths) > 1:
                raise WorkflowDefinitionError(
                    "conditional edges for one outcome must use the same artifact path"
                )
            values = [
                (type(edge.condition.equals), edge.condition.equals)
                for edge in conditional
                if edge.condition is not None
            ]
            if len(values) != len(set(values)):
                raise WorkflowDefinitionError(
                    "conditional edges for one outcome must use distinct values"
                )

        for node in self.nodes:
            if node.kind is NodeKind.TERMINAL and outgoing[node.key]:
                raise WorkflowDefinitionError("terminal nodes cannot have outgoing edges")
            if node.kind is not NodeKind.TERMINAL and not outgoing[node.key]:
                raise WorkflowDefinitionError("non-terminal nodes require an outgoing edge")
            if node.kind is NodeKind.FORK and len(adjacency[node.key]) < 2:
                raise WorkflowDefinitionError("fork nodes require at least two targets")
            if node.kind is NodeKind.JOIN:
                if node.key == self.entry_node:
                    raise WorkflowDefinitionError("join nodes cannot be workflow entry nodes")
                if len(incoming[node.key]) < 2:
                    raise WorkflowDefinitionError("join nodes require at least two sources")
            for mapping in node.input_mappings:
                source = nodes_by_key.get(mapping.source_node)
                if source is None:
                    raise WorkflowDefinitionError("node input mapping references an unknown node")
                if source.kind is not NodeKind.TASK:
                    raise WorkflowDefinitionError("node input mapping source must be a task node")
                if source.key == node.key:
                    raise WorkflowDefinitionError("node input mapping cannot reference itself")
                reachable_from_source: set[str] = set()
                pending_from_source = [source.key]
                while pending_from_source:
                    current = pending_from_source.pop()
                    if current in reachable_from_source:
                        continue
                    reachable_from_source.add(current)
                    pending_from_source.extend(adjacency[current] - reachable_from_source)
                if node.key not in reachable_from_source:
                    raise WorkflowDefinitionError(
                        "node input mapping source must precede its target in the graph"
                    )

        reachable: set[str] = set()
        pending = [self.entry_node]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(adjacency[current] - reachable)
        if reachable != set(nodes_by_key):
            raise WorkflowDefinitionError("all workflow nodes must be reachable from the entry")
        for node in self.nodes:
            if node.kind in {NodeKind.FORK, NodeKind.JOIN} and _can_reach(
                adjacency, node.key, node.key, skip_initial=True
            ):
                raise WorkflowDefinitionError("fork and join nodes cannot participate in loops")

    def node(self, key: str) -> NodeDefinition:
        return next(node for node in self.nodes if node.key == key)

    def target(self, source: str, outcome: NodeOutcome) -> str | None:
        return next(
            (
                edge.target
                for edge in self.edges
                if edge.source == source and edge.outcome is outcome and edge.condition is None
            ),
            None,
        )

    def targets(self, source: str, outcome: NodeOutcome) -> tuple[str, ...]:
        return tuple(
            sorted(
                edge.target
                for edge in self.edges
                if edge.source == source and edge.outcome is outcome
            )
        )

    def route_edges(self, source: str, outcome: NodeOutcome) -> tuple[EdgeDefinition, ...]:
        return tuple(
            edge for edge in self.edges if edge.source == source and edge.outcome is outcome
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowSnapshot:
    run_id: UUID
    definition_id: UUID
    definition_key: str
    definition_version: int
    entry_node: str
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    request_context: WorkflowRequestContext | None = None
    phase_packs: tuple[PhasePackDefinition, ...] = ()
    skills: tuple[SkillDefinition, ...] = ()
    model_selections: tuple[NodeModelSelection, ...] = ()
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        phase_packs_by_ref = {value.reference: value for value in self.phase_packs}
        if len(phase_packs_by_ref) != len(self.phase_packs):
            raise WorkflowDefinitionError("snapshot phase packs must be unique by key and version")
        required_phase_packs = {
            node.phase_pack for node in self.nodes if node.phase_pack is not None
        }
        if required_phase_packs != set(phase_packs_by_ref):
            raise WorkflowDefinitionError(
                "snapshot phase packs must exactly resolve node references"
            )
        for node in self.nodes:
            if node.phase_pack is None:
                continue
            phase_pack = phase_packs_by_ref[node.phase_pack]
            declared_inputs = {value.key: value for value in phase_pack.inputs}
            mapped_inputs = {value.input_key for value in node.input_mappings}
            if not mapped_inputs <= set(declared_inputs):
                raise WorkflowDefinitionError("node maps an undeclared phase pack input")
            required_inputs = {key for key, value in declared_inputs.items() if value.required}
            if not required_inputs <= mapped_inputs:
                raise WorkflowDefinitionError("node must map every required phase pack input")
        skills_by_ref = {skill.reference: skill for skill in self.skills}
        if len(skills_by_ref) != len(self.skills):
            raise WorkflowDefinitionError("snapshot skills must be unique by key and version")
        required = {reference for node in self.nodes for reference in node.skills}
        required.update(reference for value in self.phase_packs for reference in value.skills)
        if required != set(skills_by_ref):
            raise WorkflowDefinitionError("snapshot skills must exactly resolve node references")
        selections_by_node = {value.node_key: value for value in self.model_selections}
        if len(selections_by_node) != len(self.model_selections):
            raise WorkflowDefinitionError("snapshot model selections must be unique by node")
        required_nodes = {node.key for node in self.nodes if node.model_routing is not None}
        if required_nodes != set(selections_by_node):
            raise WorkflowDefinitionError(
                "snapshot model selections must exactly resolve node routing requests"
            )

    @classmethod
    def from_definition(
        cls,
        definition: WorkflowDefinition,
        *,
        run_id: UUID,
        request_context: WorkflowRequestContext | None = None,
        phase_packs: tuple[PhasePackDefinition, ...] = (),
        skills: tuple[SkillDefinition, ...] = (),
        model_selections: tuple[NodeModelSelection, ...] = (),
    ) -> "WorkflowSnapshot":
        return cls(
            run_id=run_id,
            definition_id=definition.id,
            definition_key=definition.key,
            definition_version=definition.version,
            entry_node=definition.entry_node,
            nodes=deepcopy(definition.nodes),
            edges=definition.edges,
            request_context=deepcopy(request_context),
            phase_packs=deepcopy(phase_packs),
            skills=deepcopy(skills),
            model_selections=deepcopy(model_selections),
        )

    def node(self, key: str) -> NodeDefinition:
        return next(node for node in self.nodes if node.key == key)

    def target(self, source: str, outcome: NodeOutcome) -> str | None:
        return next(
            (
                edge.target
                for edge in self.edges
                if edge.source == source and edge.outcome is outcome and edge.condition is None
            ),
            None,
        )

    def targets(self, source: str, outcome: NodeOutcome) -> tuple[str, ...]:
        return tuple(
            sorted(
                edge.target
                for edge in self.edges
                if edge.source == source and edge.outcome is outcome
            )
        )

    def route_edges(self, source: str, outcome: NodeOutcome) -> tuple[EdgeDefinition, ...]:
        return tuple(
            edge for edge in self.edges if edge.source == source and edge.outcome is outcome
        )

    def incoming_sources(self, target: str) -> tuple[str, ...]:
        """Return deterministic direct predecessors that may provide task artifacts."""

        return tuple(sorted({edge.source for edge in self.edges if edge.target == target}))

    def phase_pack(self, reference: PhasePackReference) -> PhasePackDefinition:
        return next(value for value in self.phase_packs if value.reference == reference)

    def skill(self, reference: SkillReference) -> SkillDefinition:
        return next(skill for skill in self.skills if skill.reference == reference)

    def model_selection(self, node_key: str) -> ModelSelection | None:
        return next(
            (value.selection for value in self.model_selections if value.node_key == node_key),
            None,
        )


@dataclass(slots=True, kw_only=True)
class NodeExecution:
    workflow_execution_id: UUID
    node_key: str
    executor_key: str = "default"
    id: UUID = field(default_factory=uuid4)
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    visit_count: int = 0
    attempt_count: int = 0
    outcome: NodeOutcome | None = None
    output: dict[str, Any] | None = None
    worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowTaskCandidate:
    """A locked READY node returned inside a repository transaction."""

    execution: "WorkflowExecution"
    node_key: str


@dataclass(slots=True, kw_only=True)
class WorkflowExecution:
    snapshot: WorkflowSnapshot
    id: UUID = field(default_factory=uuid4)
    status: WorkflowStatus = WorkflowStatus.PENDING
    nodes: dict[str, NodeExecution] = field(default_factory=dict)
    failure_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    @classmethod
    def create(cls, snapshot: WorkflowSnapshot) -> "WorkflowExecution":
        execution = cls(snapshot=snapshot)
        execution.nodes = {
            node.key: NodeExecution(
                workflow_execution_id=execution.id,
                node_key=node.key,
                executor_key=node.executor_key or "default",
            )
            for node in snapshot.nodes
        }
        return execution

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }


def _can_reach(
    adjacency: dict[str, set[str]],
    source: str,
    target: str,
    *,
    skip_initial: bool = False,
) -> bool:
    pending = list(adjacency[source]) if skip_initial else [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current] - visited)
    return False
