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
    WORKSPACE_MANAGE = "workspace.manage"
    SCM_PUBLISH = "scm.publish"
    NOTIFICATION_MANAGE = "notification.manage"
    PROJECT_ADMIN = "project.admin"


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccount:
    key: str
    name: str
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
        if not self.permissions:
            raise DomainValidationError("service account requires at least one permission")
        if not self.all_projects and not self.project_ids:
            raise DomainValidationError("service account requires a project scope")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceAccountCredential:
    account_id: UUID
    token_digest: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.token_digest) is None:
            raise DomainValidationError("service account credential digest must be SHA-256")
        created_at = self._as_utc(self.created_at)
        expires_at = self._optional_utc(self.expires_at)
        revoked_at = self._optional_utc(self.revoked_at)
        last_used_at = self._optional_utc(self.last_used_at)
        if expires_at is not None and expires_at <= created_at:
            raise DomainValidationError("credential expiration must be after creation")
        if revoked_at is not None and revoked_at < created_at:
            raise DomainValidationError("credential revocation cannot precede creation")
        if last_used_at is not None and last_used_at < created_at:
            raise DomainValidationError("credential usage cannot precede creation")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "revoked_at", revoked_at)
        object.__setattr__(self, "last_used_at", last_used_at)

    def is_active(self, at: datetime | None = None) -> bool:
        checked_at = self._as_utc(at or datetime.now(UTC))
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > checked_at)

    @staticmethod
    def _optional_utc(value: datetime | None) -> datetime | None:
        return ServiceAccountCredential._as_utc(value) if value is not None else None

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiPrincipal:
    account_id: UUID
    account_key: str
    permissions: frozenset[ApiPermission]
    project_ids: frozenset[UUID]
    all_projects: bool
    credential_id: UUID | None = None

    def allows(self, permission: ApiPermission, project_id: UUID | None = None) -> bool:
        if (
            permission not in self.permissions
            and ApiPermission.PROJECT_ADMIN not in self.permissions
        ):
            return False
        if project_id is None:
            return self.all_projects
        return self.all_projects or project_id in self.project_ids
