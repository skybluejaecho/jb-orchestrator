"""Relational persistence records for the initial orchestration domain."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from jb_orchestrator.budgets import BudgetReservationStatus, UsageKind
from jb_orchestrator.domain.projects import ProjectStatus
from jb_orchestrator.domain.requests import RequestStatus
from jb_orchestrator.domain.runs import RunStatus
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.infrastructure.database.base import Base
from jb_orchestrator.model_routing import ModelTier
from jb_orchestrator.scm import ScmPublicationStatus
from jb_orchestrator.skills import SkillSourceKind
from jb_orchestrator.workflows.models import NodeExecutionStatus, NodeOutcome, WorkflowStatus
from jb_orchestrator.workspace_operations import WorkspaceOperationKind, WorkspaceOperationStatus


def string_enum(enum_type: type[Any], name: str) -> Enum:
    """Store string enum values portably with a database check constraint."""

    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class TimestampMixin:
    """Created and last-updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProjectRecord(TimestampMixin, Base):
    """Stored project configuration."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    status: Mapped[ProjectStatus] = mapped_column(
        string_enum(ProjectStatus, "project_status"),
        nullable=False,
        default=ProjectStatus.ACTIVE,
    )

    requests: Mapped[list["UserRequestRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ServiceAccountRecord(Base):
    """Hashed bearer credential with explicit permissions and project scope."""

    __tablename__ = "service_accounts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    project_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    all_projects: Mapped[bool] = mapped_column(nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectWorkflowBindingRecord(TimestampMixin, Base):
    """Current exact workflow version selected for a project."""

    __tablename__ = "project_workflow_bindings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    definition_key: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)


class RequestDispatchReceiptRecord(Base):
    """Project-scoped idempotency claim and completed dispatch result."""

    __tablename__ = "request_dispatch_receipts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "ingress_key",
            "idempotency_key",
            name="uq_dispatch_receipts_project_ingress_key",
        ),
        CheckConstraint(
            "(request_id IS NULL AND run_id IS NULL AND workflow_execution_id IS NULL "
            "AND completed_at IS NULL) OR "
            "(request_id IS NOT NULL AND run_id IS NOT NULL "
            "AND workflow_execution_id IS NOT NULL AND completed_at IS NOT NULL)",
            name="dispatch_receipt_result_all_or_none",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    ingress_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_requests.id", ondelete="CASCADE")
    )
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    workflow_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRequestRecord(TimestampMixin, Base):
    """Stored original user intent."""

    __tablename__ = "user_requests"
    __table_args__ = (
        CheckConstraint(
            "(ingress_key IS NULL AND external_request_id IS NULL "
            "AND origin_actor_id IS NULL AND origin_conversation_id IS NULL) OR "
            "(ingress_key IS NOT NULL AND external_request_id IS NOT NULL)",
            name="user_request_origin_required_fields",
        ),
        Index("ix_user_requests_origin", "ingress_key", "external_request_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    ingress_key: Mapped[str | None] = mapped_column(String(64))
    external_request_id: Mapped[str | None] = mapped_column(String(255))
    origin_actor_id: Mapped[str | None] = mapped_column(String(255))
    origin_conversation_id: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[RequestStatus] = mapped_column(
        string_enum(RequestStatus, "request_status"),
        nullable=False,
        default=RequestStatus.RECEIVED,
    )

    project: Mapped[ProjectRecord] = relationship(back_populates="requests")
    runs: Mapped[list["RunRecord"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RunRecord(TimestampMixin, Base):
    """Stored execution attempt with optimistic concurrency control."""

    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("request_id", "attempt", name="uq_runs_request_attempt"),
        Index("ix_runs_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[RunStatus] = mapped_column(
        string_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.QUEUED
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    request: Mapped[UserRequestRecord] = relationship(back_populates="runs")

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class EventRecord(Base):
    """Append-only event emitted by a committed application use case."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_aggregate_occurred", "aggregate_id", "occurred_at"),
        Index("ix_events_aggregate_type_sequence", "aggregate_type", "sequence"),
        UniqueConstraint("id", name="uq_events_id"),
    )

    sequence: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    id: Mapped[UUID] = mapped_column(Uuid, nullable=False, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskArtifactRecord(Base):
    """Immutable output produced by one workflow task node visit."""

    __tablename__ = "task_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "producer_node_key",
            "visit_count",
            name="uq_task_artifacts_execution_node_visit",
        ),
        Index("ix_task_artifacts_execution_created", "execution_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False
    )
    producer_node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[NodeOutcome] = mapped_column(
        string_enum(NodeOutcome, "task_artifact_outcome"), nullable=False
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SkillDefinitionRecord(Base):
    """Immutable catalog entry for one skill version."""

    __tablename__ = "skill_definitions"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_skill_definitions_key_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[SkillSourceKind] = mapped_column(
        string_enum(SkillSourceKind, "skill_source_kind"), nullable=False
    )
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(255))
    entrypoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    skill_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PhasePackDefinitionRecord(Base):
    """Immutable reusable phase-pack version."""

    __tablename__ = "phase_pack_definitions"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_phase_pack_definitions_key_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    output_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    skills: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    phase_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelProfileRecord(Base):
    """Immutable catalog entry for one executable model profile version."""

    __tablename__ = "model_profiles"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_model_profiles_key_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[ModelTier] = mapped_column(string_enum(ModelTier, "model_tier"), nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    input_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    output_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    executor_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    profile_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BudgetAccountRecord(Base):
    """Mutable project-level USD budget balance."""

    __tablename__ = "budget_accounts"
    __table_args__ = (
        CheckConstraint("limit_usd >= 0", name="budget_limit_nonnegative"),
        CheckConstraint("reserved_usd >= 0", name="budget_reserved_nonnegative"),
        CheckConstraint("spent_usd >= 0", name="budget_spent_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    limit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class BudgetReservationRecord(Base):
    """Idempotent maximum-cost reservation for one logical task visit."""

    __tablename__ = "budget_reservations"
    __table_args__ = (
        CheckConstraint("reserved_usd >= 0", name="reservation_amount_nonnegative"),
        CheckConstraint(
            "actual_usd IS NULL OR actual_usd >= 0",
            name="reservation_actual_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("budget_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[BudgetReservationStatus] = mapped_column(
        string_enum(BudgetReservationStatus, "budget_reservation_status"), nullable=False
    )
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageRecordRecord(Base):
    """Append-only actual or conservative model usage charge."""

    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="usage_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="usage_output_tokens_nonnegative"),
        CheckConstraint("cost_usd >= 0", name="usage_cost_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("budget_reservations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("budget_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[UsageKind] = mapped_column(string_enum(UsageKind, "usage_kind"), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    model_profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExternalExecutionRecord(Base):
    """Retry-safe mapping to one external runtime execution."""

    __tablename__ = "external_executions"
    __table_args__ = (
        UniqueConstraint(
            "executor_key",
            "external_run_id",
            name="uq_external_executions_executor_run",
        ),
        Index("ix_external_executions_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    executor_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    external_session_key: Mapped[str] = mapped_column(String(512), nullable=False)
    external_agent_id: Mapped[str | None] = mapped_column(String(255))
    workspace_path: Mapped[str | None] = mapped_column(String(2048))
    workspace_repository_path: Mapped[str | None] = mapped_column(String(2048))
    workspace_branch: Mapped[str | None] = mapped_column(String(255))
    workspace_base_ref: Mapped[str | None] = mapped_column(String(255))
    workspace_scope: Mapped[str | None] = mapped_column(String(128), index=True)
    workspace_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_run_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ExternalExecutionStatus] = mapped_column(
        string_enum(ExternalExecutionStatus, "external_execution_status"), nullable=False
    )
    terminal_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceOperationRecord(Base):
    """Leaseable command for maintenance of an executor-owned workspace."""

    __tablename__ = "workspace_operations"
    __table_args__ = (
        UniqueConstraint(
            "external_execution_id",
            "idempotency_key",
            name="uq_workspace_operations_execution_key",
        ),
        Index("ix_workspace_operations_claim", "workspace_scope", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    external_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[WorkspaceOperationKind] = mapped_column(
        string_enum(WorkspaceOperationKind, "workspace_operation_kind"), nullable=False
    )
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[WorkspaceOperationStatus] = mapped_column(
        string_enum(WorkspaceOperationStatus, "workspace_operation_status"), nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScmPublicationRecord(Base):
    """Leaseable request to publish one executor-owned branch for review."""

    __tablename__ = "scm_publications"
    __table_args__ = (
        UniqueConstraint(
            "external_execution_id",
            "idempotency_key",
            name="uq_scm_publications_execution_key",
        ),
        Index(
            "ix_scm_publications_claim",
            "provider_key",
            "workspace_scope",
            "status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    external_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    repository: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ScmPublicationStatus] = mapped_column(
        string_enum(ScmPublicationStatus, "scm_publication_status"), nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowDefinitionRecord(Base):
    """Versioned workflow graph definition."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_workflow_definitions_key_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkflowExecutionRecord(Base):
    """Durable workflow status and immutable snapshot."""

    __tablename__ = "workflow_executions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        string_enum(WorkflowStatus, "workflow_status"),
        nullable=False,
        default=WorkflowStatus.PENDING,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    nodes: Mapped[list["NodeExecutionRecord"]] = relationship(
        back_populates="workflow_execution", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class NodeExecutionRecord(Base):
    """Durable state for one workflow node across visits and attempts."""

    __tablename__ = "node_executions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_execution_id",
            "node_key",
            name="uq_node_executions_workflow_node",
        ),
        Index("ix_node_executions_status_updated", "status", "updated_at"),
        Index(
            "ix_node_executions_lease_expiry",
            "status",
            "lease_expires_at",
            postgresql_where=text("lease_expires_at IS NOT NULL"),
        ),
        Index(
            "ix_node_executions_executor_ready",
            "executor_key",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    executor_key: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    status: Mapped[NodeExecutionStatus] = mapped_column(
        string_enum(NodeExecutionStatus, "node_execution_status"), nullable=False
    )
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome: Mapped[NodeOutcome | None] = mapped_column(
        string_enum(NodeOutcome, "node_outcome"), nullable=True
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    workflow_execution: Mapped[WorkflowExecutionRecord] = relationship(back_populates="nodes")
