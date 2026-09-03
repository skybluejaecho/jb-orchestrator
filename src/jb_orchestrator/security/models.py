"""Service-account identities and API permissions."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError

ACCOUNT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")


class ApiPermission(StrEnum):
    PROJECT_READ = "project.read"
    REQUEST_DISPATCH = "request.dispatch"
    WORKFLOW_APPROVE = "workflow.approve"
    RUN_CANCEL = "run.cancel"
    PROJECT_ADMIN = "project.admin"


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccount:
    key: str
    name: str
    token_digest: str
    permissions: frozenset[ApiPermission]
    project_ids: frozenset[UUID] = frozenset()
    all_projects: bool = False
    enabled: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        key = self.key.strip()
        name = self.name.strip()
        if not ACCOUNT_KEY_PATTERN.fullmatch(key):
            raise DomainValidationError("service account key is invalid")
        if not name or len(name) > 255:
            raise DomainValidationError("service account name must contain 1-255 characters")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.token_digest) is None:
            raise DomainValidationError("service account token digest must be SHA-256")
        if not self.permissions:
            raise DomainValidationError("service account requires at least one permission")
        if not self.all_projects and not self.project_ids:
            raise DomainValidationError("service account requires a project scope")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiPrincipal:
    account_id: UUID
    account_key: str
    permissions: frozenset[ApiPermission]
    project_ids: frozenset[UUID]
    all_projects: bool

    def allows(self, permission: ApiPermission, project_id: UUID | None = None) -> bool:
        if (
            permission not in self.permissions
            and ApiPermission.PROJECT_ADMIN not in self.permissions
        ):
            return False
        if project_id is None:
            return self.all_projects
        return self.all_projects or project_id in self.project_ids
