"""Worker/executor boundary models."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.model_routing import ModelSelection
from jb_orchestrator.phase_packs import PhasePackDefinition
from jb_orchestrator.skills import SkillDefinition
from jb_orchestrator.workflows import NodeOutcome, WorkflowRequestContext


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskArtifactInput:
    """A named phase input resolved to one immutable artifact."""

    name: str
    artifact: TaskArtifact


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskContextEnvelope:
    """Pinned request context plus direct durable inputs for one task claim."""

    request: WorkflowRequestContext
    upstream_artifacts: tuple[TaskArtifact, ...] = ()
    named_inputs: tuple[TaskArtifactInput, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "upstream_artifacts", deepcopy(self.upstream_artifacts))
        object.__setattr__(self, "named_inputs", deepcopy(self.named_inputs))


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskClaim:
    """An executor-safe view of one leased workflow task."""

    execution_id: UUID
    run_id: UUID
    node_key: str
    executor_key: str
    worker_id: str
    lease_token: UUID
    idempotency_key: str
    visit_count: int
    attempt_count: int
    timeout_seconds: int
    workflow_key: str
    workflow_version: int
    instructions: str | None
    configuration: dict[str, Any]
    skills: tuple[SkillDefinition, ...]
    phase_pack: PhasePackDefinition | None = None
    context: TaskContextEnvelope | None = None
    model_selection: ModelSelection | None = None
    skill_paths: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenUsage:
    """Provider-reported billable token usage for one task result."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token usage must not be negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskResult:
    """Business outcome reported by an executor."""

    outcome: NodeOutcome
    output: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {NodeOutcome.SUCCESS, NodeOutcome.FAILURE}:
            raise ValueError("task result outcome must be success or failure")


@runtime_checkable
class TaskExecutor(Protocol):
    """Adapter contract implemented by Codex, Orca, OpenClaw, or test executors."""

    async def execute(self, claim: TaskClaim) -> TaskResult: ...


@runtime_checkable
class CancellableTaskExecutor(Protocol):
    """Optional hook for stopping provider-side work after local cancellation."""

    async def cancel(self, claim: TaskClaim) -> None: ...
