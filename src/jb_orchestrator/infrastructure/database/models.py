"""Relational persistence records for the initial orchestration domain."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from jb_orchestrator.domain.projects import ProjectStatus
from jb_orchestrator.domain.requests import RequestStatus
from jb_orchestrator.domain.runs import RunStatus
from jb_orchestrator.infrastructure.database.base import Base
from jb_orchestrator.workflows.models import NodeExecutionStatus, NodeOutcome, WorkflowStatus


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


class UserRequestRecord(TimestampMixin, Base):
    """Stored original user intent."""

    __tablename__ = "user_requests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
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
    __table_args__ = (Index("ix_events_aggregate_occurred", "aggregate_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[NodeExecutionStatus] = mapped_column(
        string_enum(NodeExecutionStatus, "node_execution_status"), nullable=False
    )
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome: Mapped[NodeOutcome | None] = mapped_column(
        string_enum(NodeOutcome, "node_outcome"), nullable=True
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    workflow_execution: Mapped[WorkflowExecutionRecord] = relationship(back_populates="nodes")
