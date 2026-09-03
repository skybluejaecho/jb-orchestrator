"""Transport-neutral provenance for user requests."""

import re
from dataclasses import dataclass

from jb_orchestrator.domain.exceptions import DomainValidationError

INGRESS_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestOrigin:
    """Immutable identity supplied by a request ingress adapter."""

    ingress_key: str
    external_request_id: str
    actor_id: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        ingress_key = self.ingress_key.strip()
        external_request_id = self.external_request_id.strip()
        actor_id = self.actor_id.strip() if self.actor_id else None
        conversation_id = self.conversation_id.strip() if self.conversation_id else None
        if not INGRESS_KEY_PATTERN.fullmatch(ingress_key):
            raise DomainValidationError(
                "ingress key must be 1-64 lowercase letters, digits, dots, underscores, or hyphens"
            )
        if not external_request_id or len(external_request_id) > 255:
            raise DomainValidationError("external request ID must contain 1-255 characters")
        if actor_id is not None and len(actor_id) > 255:
            raise DomainValidationError("origin actor ID must contain at most 255 characters")
        if conversation_id is not None and len(conversation_id) > 512:
            raise DomainValidationError(
                "origin conversation ID must contain at most 512 characters"
            )
        object.__setattr__(self, "ingress_key", ingress_key)
        object.__setattr__(self, "external_request_id", external_request_id)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "conversation_id", conversation_id)
