"""Stable JSON representation for skill catalog entries."""

from datetime import datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.skills import SkillDefinition, SkillSourceKind


def skill_to_dict(skill: SkillDefinition) -> dict[str, Any]:
    return {
        "id": str(skill.id),
        "key": skill.key,
        "version": skill.version,
        "name": skill.name,
        "description": skill.description,
        "source_kind": skill.source_kind.value,
        "source_uri": skill.source_uri,
        "content_digest": skill.content_digest,
        "source_revision": skill.source_revision,
        "entrypoint": skill.entrypoint,
        "metadata": skill.metadata,
        "created_at": skill.created_at.isoformat(),
    }


def skill_from_dict(data: dict[str, Any]) -> SkillDefinition:
    return SkillDefinition(
        id=UUID(str(data["id"])),
        key=str(data["key"]),
        version=int(data["version"]),
        name=str(data["name"]),
        description=str(data["description"]),
        source_kind=SkillSourceKind(str(data["source_kind"])),
        source_uri=str(data["source_uri"]),
        content_digest=str(data["content_digest"]),
        source_revision=(str(data["source_revision"]) if data.get("source_revision") else None),
        entrypoint=str(data["entrypoint"]),
        metadata=dict(data.get("metadata", {})),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )
