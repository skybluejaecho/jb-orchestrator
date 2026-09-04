"""Application command payloads."""

from dataclasses import dataclass
from uuid import UUID

from jb_orchestrator.domain import RequestOrigin
from jb_orchestrator.skills import SkillReference


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeSkillAddon:
    """Exact Skills added to one task node for a single request."""

    node_key: str
    skills: tuple[SkillReference, ...]


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


@dataclass(frozen=True, slots=True, kw_only=True)
class DispatchProjectRequest:
    """Transport-neutral command accepted by every request ingress adapter."""

    project_id: UUID
    prompt: str
    idempotency_key: str
    origin: RequestOrigin
    title: str | None = None
    definition_key: str | None = None
    definition_version: int | None = None
    skill_addons: tuple[NodeSkillAddon, ...] = ()
