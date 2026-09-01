"""Versioned reusable skill catalog models."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SKILL_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SkillSourceKind(StrEnum):
    LOCAL = "local"
    GIT = "git"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillReference:
    key: str
    version: int

    def __post_init__(self) -> None:
        if not SKILL_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError("skill reference key is invalid")
        if self.version < 1:
            raise DomainValidationError("skill reference version must be greater than zero")


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillDefinition:
    key: str
    version: int
    name: str
    description: str
    source_kind: SkillSourceKind
    source_uri: str
    content_digest: str
    source_revision: str | None = None
    entrypoint: str = "SKILL.md"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for label, value in {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "source_uri": self.source_uri,
            "entrypoint": self.entrypoint,
        }.items():
            if not value.strip():
                raise DomainValidationError(f"skill {label} must not be empty")
        if self.version < 1:
            raise DomainValidationError("skill version must be greater than zero")
        if not SKILL_KEY_PATTERN.fullmatch(self.key):
            raise DomainValidationError(
                "skill key must contain only lowercase letters, digits, dot, underscore, or hyphen"
            )
        if not SHA256_PATTERN.fullmatch(self.content_digest):
            raise DomainValidationError("skill content_digest must be sha256:<64 lowercase hex>")
        if self.source_kind is SkillSourceKind.GIT and not (
            self.source_revision and self.source_revision.strip()
        ):
            raise DomainValidationError("git skill source_revision must not be empty")
        entrypoint_parts = self.entrypoint.split("/")
        if self.entrypoint.startswith("/") or "\\" in self.entrypoint or ".." in entrypoint_parts:
            raise DomainValidationError("skill entrypoint must be a safe relative POSIX path")
        try:
            json.dumps(self.metadata)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("skill metadata must be JSON serializable") from exc
        object.__setattr__(self, "metadata", deepcopy(self.metadata))

    @property
    def reference(self) -> SkillReference:
        return SkillReference(key=self.key, version=self.version)
