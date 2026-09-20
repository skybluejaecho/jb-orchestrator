"""User request aggregate."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition
from jb_orchestrator.domain.ingress import RequestOrigin


class RequestStatus(StrEnum):
    """High-level lifecycle of a user request."""

    RECEIVED = "received"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ALLOWED_REQUEST_TRANSITIONS: Final[dict[RequestStatus, frozenset[RequestStatus]]] = {
    RequestStatus.RECEIVED: frozenset({RequestStatus.ACTIVE, RequestStatus.CANCELLED}),
    RequestStatus.ACTIVE: frozenset({RequestStatus.COMPLETED, RequestStatus.CANCELLED}),
    RequestStatus.COMPLETED: frozenset(),
    RequestStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True, kw_only=True)
class UserRequest:
    """The immutable user intent that starts one or more runs."""

    project_id: UUID
    prompt: str
    title: str | None = None
    origin: RequestOrigin | None = None
    id: UUID = field(default_factory=uuid4)
    status: RequestStatus = RequestStatus.RECEIVED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.prompt = self.prompt.strip()
        self.title = self.title.strip() if self.title else None
        if not self.prompt:
            raise DomainValidationError("request prompt must not be empty")

    def activate(self, *, at: datetime | None = None) -> None:
        """Mark the request as having an active run."""

        self._set_status(RequestStatus.ACTIVE, at=at)

    def complete(self, *, at: datetime | None = None) -> None:
        """Mark the request as successfully completed."""

        self._set_status(RequestStatus.COMPLETED, at=at)

    def cancel(self, *, at: datetime | None = None) -> None:
        """Cancel the request."""

        self._set_status(RequestStatus.CANCELLED, at=at)

    def _set_status(self, status: RequestStatus, *, at: datetime | None) -> None:
        if status not in ALLOWED_REQUEST_TRANSITIONS[self.status]:
            raise InvalidStateTransition(
                f"cannot transition request from {self.status} to {status}"
            )
        self.status = status
        self.updated_at = at or datetime.now(UTC)
