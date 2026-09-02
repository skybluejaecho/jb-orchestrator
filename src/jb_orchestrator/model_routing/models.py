"""Versioned model profiles and immutable routing decisions."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError

MODEL_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ModelTier(StrEnum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    ADVANCED = "advanced"


class RequirementLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelProfile:
    key: str
    version: int
    name: str
    provider: str
    model_id: str
    tier: ModelTier
    context_window: int
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal
    enabled: bool = True
    capabilities: tuple[str, ...] = ()
    executor_keys: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for label, value in {
            "key": self.key,
            "name": self.name,
            "provider": self.provider,
            "model_id": self.model_id,
        }.items():
            if not value.strip():
                raise DomainValidationError(f"model profile {label} must not be empty")
        if not MODEL_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError("model profile key is invalid")
        if self.version < 1:
            raise DomainValidationError("model profile version must be greater than zero")
        if self.context_window < 1:
            raise DomainValidationError("model context_window must be greater than zero")
        input_cost = Decimal(str(self.input_cost_per_million)).normalize()
        output_cost = Decimal(str(self.output_cost_per_million)).normalize()
        if input_cost < 0 or output_cost < 0:
            raise DomainValidationError("model token costs must not be negative")
        capabilities = tuple(sorted(set(self.capabilities)))
        if any(not CAPABILITY_PATTERN.fullmatch(item) for item in capabilities):
            raise DomainValidationError("model capabilities contain an invalid key")
        executor_keys = tuple(sorted(set(self.executor_keys)))
        if any(not MODEL_KEY_PATTERN.fullmatch(item) for item in executor_keys):
            raise DomainValidationError("model executor_keys contain an invalid key")
        try:
            json.dumps(self.metadata)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("model metadata must be JSON serializable") from exc
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "executor_keys", executor_keys)
        object.__setattr__(self, "input_cost_per_million", input_cost)
        object.__setattr__(self, "output_cost_per_million", output_cost)
        object.__setattr__(self, "metadata", deepcopy(self.metadata))


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRoutingRequest:
    complexity: RequirementLevel = RequirementLevel.MEDIUM
    risk: RequirementLevel = RequirementLevel.MEDIUM
    quality: RequirementLevel = RequirementLevel.MEDIUM
    required_capabilities: tuple[str, ...] = ()
    estimated_input_tokens: int = 0
    max_output_tokens: int = 4096
    max_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        capabilities = tuple(sorted(set(self.required_capabilities)))
        if any(not CAPABILITY_PATTERN.fullmatch(item) for item in capabilities):
            raise DomainValidationError("routing capabilities contain an invalid key")
        if self.estimated_input_tokens < 0:
            raise DomainValidationError("estimated_input_tokens must not be negative")
        if self.max_output_tokens < 1:
            raise DomainValidationError("max_output_tokens must be greater than zero")
        if self.max_cost_usd is not None:
            budget = Decimal(str(self.max_cost_usd)).normalize()
            if budget < 0:
                raise DomainValidationError("max_cost_usd must not be negative")
            object.__setattr__(self, "max_cost_usd", budget)
        object.__setattr__(self, "required_capabilities", capabilities)

    @property
    def required_context(self) -> int:
        return self.estimated_input_tokens + self.max_output_tokens


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSelection:
    profile: ModelProfile
    policy_version: int
    required_tier: ModelTier
    estimated_cost_usd: Decimal
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeModelSelection:
    node_key: str
    selection: ModelSelection

    def __post_init__(self) -> None:
        if not self.node_key.strip():
            raise DomainValidationError("model selection node_key must not be empty")
