"""Durable task output artifact models."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.workflows import NodeOutcome


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskArtifact:
    """One immutable task result identified by workflow node visit."""

    execution_id: UUID
    producer_node_key: str
    visit_count: int
    outcome: NodeOutcome
    content: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.producer_node_key.strip():
            raise DomainValidationError("artifact producer node key must not be empty")
        if self.visit_count < 1:
            raise DomainValidationError("artifact visit count must be greater than zero")
        if self.outcome not in {NodeOutcome.SUCCESS, NodeOutcome.FAILURE}:
            raise DomainValidationError("task artifact outcome must be success or failure")
        object.__setattr__(self, "content", deepcopy(self.content))
