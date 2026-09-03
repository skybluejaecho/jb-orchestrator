"""Project-level workflow selection."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError

WORKFLOW_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(slots=True, kw_only=True)
class ProjectWorkflowBinding:
    """Exact workflow definition selected for future project requests."""

    project_id: UUID
    definition_id: UUID
    definition_key: str
    definition_version: int
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.definition_key = self.definition_key.strip()
        if not WORKFLOW_KEY_PATTERN.fullmatch(self.definition_key):
            raise DomainValidationError("workflow definition key has an invalid format")
        if self.definition_version < 1:
            raise DomainValidationError("workflow definition version must be greater than zero")


class ProjectWorkflowBindingRepository(Protocol):
    """Persistence contract for one current binding per project."""

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> ProjectWorkflowBinding | None: ...

    async def save(self, binding: ProjectWorkflowBinding) -> None: ...
