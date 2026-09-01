"""HTTP request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from jb_orchestrator.domain import ProjectStatus, RequestStatus, RunStatus


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


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
