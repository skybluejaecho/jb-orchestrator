"""Reusable phase instructions and typed artifact contracts."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError
from jb_orchestrator.skills import SkillReference

PHASE_PACK_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
INPUT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhasePackReference:
    key: str
    version: int

    def __post_init__(self) -> None:
        if not PHASE_PACK_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError("phase pack reference key is invalid")
        if self.version < 1:
            raise DomainValidationError("phase pack reference version must be greater than zero")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseInputDefinition:
    """One named input expected by a phase, independent of a workflow graph."""

    key: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        if not INPUT_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError("phase input key must be lower snake_case")
        if not self.description.strip():
            raise DomainValidationError("phase input description must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhasePackDefinition:
    """Immutable reusable role, instructions, skills, and I/O contract."""

    key: str
    version: int
    name: str
    description: str
    instructions: str
    inputs: tuple[PhaseInputDefinition, ...] = ()
    output_contract: dict[str, Any] = field(default_factory=dict)
    skills: tuple[SkillReference, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not PHASE_PACK_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError("phase pack key is invalid")
        if self.version < 1:
            raise DomainValidationError("phase pack version must be greater than zero")
        for label, value in {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
        }.items():
            if not value.strip():
                raise DomainValidationError(f"phase pack {label} must not be empty")
        if len({value.key for value in self.inputs}) != len(self.inputs):
            raise DomainValidationError("phase pack input keys must be unique")
        if len(set(self.skills)) != len(self.skills):
            raise DomainValidationError("phase pack skill references must be unique")
        try:
            json.dumps(self.output_contract)
            json.dumps(self.metadata)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("phase pack contracts must be JSON serializable") from exc
        object.__setattr__(self, "output_contract", deepcopy(self.output_contract))
        object.__setattr__(self, "metadata", deepcopy(self.metadata))

    @property
    def reference(self) -> PhasePackReference:
        return PhasePackReference(key=self.key, version=self.version)
