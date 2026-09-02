"""HTTP request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from jb_orchestrator.budgets import UsageKind
from jb_orchestrator.domain import ProjectStatus, RequestStatus, RunStatus
from jb_orchestrator.model_routing import ModelTier
from jb_orchestrator.skills import SkillSourceKind


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


class UserRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    prompt: str
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


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
