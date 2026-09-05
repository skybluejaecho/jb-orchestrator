"""HTTP request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from jb_orchestrator.budgets import UsageKind
from jb_orchestrator.domain import ProjectStatus, RequestStatus, RunStatus
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.model_routing import ModelTier, RequirementLevel
from jb_orchestrator.scm import ScmPublicationFailureCode, ScmPublicationStatus
from jb_orchestrator.skills import SkillSourceKind
from jb_orchestrator.workflows import (
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowStatus,
)
from jb_orchestrator.workspace_operations import WorkspaceOperationKind, WorkspaceOperationStatus


class ProjectCreate(BaseModel):
    key: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    repository_url: HttpUrl
    default_branch: str = Field(default="main", min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    repository_url: str
    default_branch: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class UserRequestCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    prompt: str = Field(min_length=1)


class WorkflowSelectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    definition_version: int = Field(ge=1)


class ProjectRequestDispatchCreate(UserRequestCreate):
    workflow: WorkflowSelectionPayload | None = None
    skill_addons: tuple["NodeSkillAddonPayload", ...] = Field(default=(), max_length=64)


class RequestOriginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingress_key: str
    external_request_id: str
    actor_id: str | None
    conversation_id: str | None


class UserRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    prompt: str
    origin: RequestOriginResponse | None
    status: RequestStatus
    created_at: datetime
    updated_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    attempt: int
    status: RunStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    version: int


class CreatedRequestResponse(BaseModel):
    request: UserRequestResponse
    run: RunResponse


class ProjectWorkflowBindingConfigure(BaseModel):
    definition_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    definition_version: int = Field(ge=1)


class ProjectWorkflowBindingResponse(ProjectWorkflowBindingConfigure):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    definition_id: UUID
    created_at: datetime
    updated_at: datetime


class SkillCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    source_kind: SkillSourceKind
    source_uri: str = Field(min_length=1, max_length=2048)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_revision: str | None = Field(default=None, min_length=1, max_length=255)
    entrypoint: str = Field(default="SKILL.md", min_length=1, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    version: int
    name: str
    description: str
    source_kind: SkillSourceKind
    source_uri: str
    content_digest: str
    source_revision: str | None
    entrypoint: str
    metadata: dict[str, Any]
    created_at: datetime


class ModelProfileCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=255)
    tier: ModelTier
    context_window: int = Field(ge=1)
    input_cost_per_million: Decimal = Field(ge=0)
    output_cost_per_million: Decimal = Field(ge=0)
    enabled: bool = True
    capabilities: tuple[str, ...] = ()
    executor_keys: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    version: int
    name: str
    provider: str
    model_id: str
    tier: ModelTier
    context_window: int
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal
    enabled: bool
    capabilities: tuple[str, ...]
    executor_keys: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: datetime


class BudgetConfigure(BaseModel):
    limit_usd: Decimal = Field(ge=0)


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    limit_usd: Decimal
    reserved_usd: Decimal
    spent_usd: Decimal
    available_usd: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


class UsageRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reservation_id: UUID
    project_id: UUID
    run_id: UUID
    execution_id: UUID
    node_key: str
    kind: UsageKind
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    model_profile_key: str
    model_profile_version: int
    recorded_at: datetime


class ExternalExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    run_id: UUID
    node_key: str
    executor_key: str
    idempotency_key: str
    external_session_key: str
    external_agent_id: str | None
    workspace_path: str | None
    workspace_repository_path: str | None
    workspace_branch: str | None
    workspace_base_ref: str | None
    workspace_scope: str | None
    workspace_released_at: datetime | None
    external_run_id: str | None
    status: ExternalExecutionStatus
    terminal_result: dict[str, Any] | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class WorkspaceOperationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: WorkspaceOperationKind
    target_ref: str = Field(min_length=1, max_length=255)
    confirmation: str | None = Field(default=None, max_length=36)


class WorkspaceOperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_execution_id: UUID
    kind: WorkspaceOperationKind
    target_ref: str
    idempotency_key: str
    requested_by: str
    status: WorkspaceOperationStatus
    worker_id: str | None
    result: dict[str, Any] | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ScmPublicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_key: str = Field(pattern=r"^[a-z][a-z0-9._-]*$", max_length=64)
    target_branch: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(default="", max_length=65535)


class ScmPublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_execution_id: UUID
    provider_key: str
    repository: str
    source_branch: str
    target_branch: str
    title: str
    body: str
    idempotency_key: str
    requested_by: str
    status: ScmPublicationStatus
    worker_id: str | None
    result: dict[str, Any] | None
    failure_reason: str | None
    failure_code: ScmPublicationFailureCode | None
    failure_retryable: bool | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class SkillReferencePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)


class NodeSkillAddonPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_key: str = Field(min_length=1, max_length=128)
    skills: tuple[SkillReferencePayload, ...] = Field(min_length=1, max_length=64)


class PhaseInputPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=128)
    description: str = Field(min_length=1)
    required: bool = True


class PhasePackReferencePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)


class PhasePackCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    inputs: tuple[PhaseInputPayload, ...] = ()
    output_contract: dict[str, Any] = Field(default_factory=dict)
    skills: tuple[SkillReferencePayload, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhasePackResponse(PhasePackCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class NodeInputMappingPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    input_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=128)
    source_node: str = Field(min_length=1, max_length=128)


class ModelRoutingPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    complexity: RequirementLevel = RequirementLevel.MEDIUM
    risk: RequirementLevel = RequirementLevel.MEDIUM
    quality: RequirementLevel = RequirementLevel.MEDIUM
    required_capabilities: tuple[str, ...] = ()
    estimated_input_tokens: int = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=4096, ge=1)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)


class WorkflowNodePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(min_length=1, max_length=128)
    kind: NodeKind
    max_attempts: int = Field(default=1, ge=1)
    max_visits: int = Field(default=1, ge=1)
    timeout_seconds: int = Field(default=600, ge=1)
    terminal_status: WorkflowStatus | None = None
    executor_key: str | None = Field(default=None, min_length=1, max_length=128)
    instructions: str | None = Field(default=None, min_length=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
    skills: tuple[SkillReferencePayload, ...] = ()
    model_routing: ModelRoutingPayload | None = None
    phase_pack: PhasePackReferencePayload | None = None
    input_mappings: tuple[NodeInputMappingPayload, ...] = ()


class ArtifactConditionPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    path: str = Field(pattern=r"^(?:/(?:[^~/]|~[01])*)+$", max_length=512)
    equals: str | int | float | bool | None


class WorkflowEdgePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = Field(min_length=1, max_length=128)
    outcome: NodeOutcome
    target: str = Field(min_length=1, max_length=128)
    condition: ArtifactConditionPayload | None = None


class WorkflowDefinitionCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int = Field(ge=1)
    entry_node: str = Field(min_length=1, max_length=128)
    nodes: tuple[WorkflowNodePayload, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdgePayload, ...] = ()


class WorkflowDefinitionResponse(WorkflowDefinitionCreate):
    id: UUID


class WorkflowOptionResponse(BaseModel):
    id: UUID
    key: str
    version: int
    entry_node: str
    nodes: tuple[WorkflowNodePayload, ...]
    edges: tuple[WorkflowEdgePayload, ...]
    phase_packs: tuple["WorkflowPhasePackSummaryResponse", ...] = ()
    skills: tuple["WorkflowSkillSummaryResponse", ...] = ()


class WorkflowPhasePackSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    version: int
    name: str
    description: str
    skills: tuple[SkillReferencePayload, ...] = ()


class WorkflowSkillSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    version: int
    name: str
    description: str
    source_kind: SkillSourceKind


class ProjectWorkflowOptionsResponse(BaseModel):
    default: ProjectWorkflowBindingResponse | None
    default_workflow: WorkflowOptionResponse | None
    workflows: tuple[WorkflowOptionResponse, ...]
    available_skills: tuple[WorkflowSkillSummaryResponse, ...]


class WorkflowStart(BaseModel):
    definition_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    version: int | None = Field(default=None, ge=1)


class WorkflowApprovalResolve(BaseModel):
    approved: bool


class WorkflowRequestContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    project_id: UUID
    project_key: str
    project_name: str
    repository_url: str
    default_branch: str
    prompt: str
    title: str | None


class TaskArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    producer_node_key: str
    visit_count: int
    outcome: NodeOutcome
    content: dict[str, Any]
    created_at: datetime


class NodeExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_key: str
    executor_key: str
    status: NodeExecutionStatus
    visit_count: int
    attempt_count: int
    outcome: NodeOutcome | None
    output: dict[str, Any] | None
    worker_id: str | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class WorkflowExecutionResponse(BaseModel):
    id: UUID
    run_id: UUID
    snapshot_id: UUID
    definition_key: str
    definition_version: int
    request_context: WorkflowRequestContextResponse | None
    status: WorkflowStatus
    nodes: tuple[NodeExecutionResponse, ...]
    failure_reason: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    version: int


class DispatchedRequestResponse(BaseModel):
    request: UserRequestResponse
    run: RunResponse
    workflow: WorkflowExecutionResponse
    replayed: bool


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
