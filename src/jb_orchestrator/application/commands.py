"""Application command payloads."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterProject:
    key: str
    name: str
    repository_url: str
    default_branch: str = "main"


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateUserRequest:
    project_id: UUID
    prompt: str
    title: str | None = None
