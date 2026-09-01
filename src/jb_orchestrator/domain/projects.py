"""Project aggregate."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError

PROJECT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")


class ProjectStatus(StrEnum):
    """Project availability within the orchestrator."""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(slots=True, kw_only=True)
class Project:
    """A source repository registered with the orchestrator."""

    key: str
    name: str
    repository_url: str
    default_branch: str = "main"
    id: UUID = field(default_factory=uuid4)
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.key = self.key.strip()
        self.name = self.name.strip()
        self.repository_url = self.repository_url.strip()
        self.default_branch = self.default_branch.strip()

        if not PROJECT_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError(
                "project key must be 3-64 lowercase letters, digits, or hyphens"
            )
        if not self.name:
            raise DomainValidationError("project name must not be empty")
        if not self.repository_url:
            raise DomainValidationError("repository URL must not be empty")
        if not self.default_branch:
            raise DomainValidationError("default branch must not be empty")

    def archive(self, *, at: datetime | None = None) -> None:
        """Prevent new work from being scheduled for this project."""

        self.status = ProjectStatus.ARCHIVED
        self.updated_at = at or datetime.now(UTC)
