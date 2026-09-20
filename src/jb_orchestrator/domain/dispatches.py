"""Idempotent user request dispatch receipts."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError


@dataclass(slots=True, kw_only=True)
class RequestDispatchReceipt:
    """Durable ownership and result of one project-scoped idempotency key."""

    project_id: UUID
    idempotency_key: str
    payload_digest: str
    ingress_key: str = "legacy"
    id: UUID = field(default_factory=uuid4)
    request_id: UUID | None = None
    run_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.idempotency_key = self.idempotency_key.strip()
        self.ingress_key = self.ingress_key.strip()
        if re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", self.ingress_key) is None:
            raise DomainValidationError("dispatch receipt ingress key is invalid")
        if not self.idempotency_key or len(self.idempotency_key) > 128:
            raise DomainValidationError("idempotency key must contain 1-128 characters")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.payload_digest) is None:
            raise DomainValidationError("dispatch payload digest must be a SHA-256 digest")
        result_ids = (self.request_id, self.run_id, self.workflow_execution_id)
        if any(value is not None for value in result_ids) and not all(
            value is not None for value in result_ids
        ):
            raise DomainValidationError("dispatch receipt result identifiers must be all or none")
        if self.completed_at is not None and not self.is_complete:
            raise DomainValidationError("completed dispatch receipt requires result identifiers")

    @property
    def is_complete(self) -> bool:
        return all(
            value is not None
            for value in (self.request_id, self.run_id, self.workflow_execution_id)
        )

    def complete(
        self,
        *,
        request_id: UUID,
        run_id: UUID,
        workflow_execution_id: UUID,
        at: datetime | None = None,
    ) -> None:
        if self.is_complete:
            raise DomainValidationError("dispatch receipt is already complete")
        self.request_id = request_id
        self.run_id = run_id
        self.workflow_execution_id = workflow_execution_id
        self.completed_at = at or datetime.now(UTC)


class RequestDispatchReceiptRepository(Protocol):
    """Persistence contract for atomic dispatch-key ownership."""

    async def try_claim(self, receipt: RequestDispatchReceipt) -> bool: ...

    async def get(
        self,
        project_id: UUID,
        ingress_key: str,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> RequestDispatchReceipt | None: ...

    async def save(self, receipt: RequestDispatchReceipt) -> None: ...
