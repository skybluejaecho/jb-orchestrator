"""Stable JSON representation for phase packs embedded in snapshots."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.phase_packs.models import PhaseInputDefinition, PhasePackDefinition
from jb_orchestrator.skills import SkillReference


def phase_pack_to_dict(phase_pack: PhasePackDefinition) -> dict[str, Any]:
    return {
        "id": str(phase_pack.id),
        "key": phase_pack.key,
        "version": phase_pack.version,
        "name": phase_pack.name,
        "description": phase_pack.description,
        "instructions": phase_pack.instructions,
        "inputs": [
            {"key": value.key, "description": value.description, "required": value.required}
            for value in phase_pack.inputs
        ],
        "output_contract": phase_pack.output_contract,
        "skills": [
            {"key": reference.key, "version": reference.version} for reference in phase_pack.skills
        ],
        "metadata": phase_pack.metadata,
        "created_at": phase_pack.created_at.isoformat(),
    }


def phase_pack_from_dict(data: dict[str, Any]) -> PhasePackDefinition:
    created_at = datetime.fromisoformat(str(data["created_at"]))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    return PhasePackDefinition(
        id=UUID(str(data["id"])),
        key=str(data["key"]),
        version=int(data["version"]),
        name=str(data["name"]),
        description=str(data["description"]),
        instructions=str(data["instructions"]),
        inputs=tuple(
            PhaseInputDefinition(
                key=str(value["key"]),
                description=str(value["description"]),
                required=bool(value.get("required", True)),
            )
            for value in data.get("inputs", [])
        ),
        output_contract=dict(data.get("output_contract", {})),
        skills=tuple(
            SkillReference(key=str(value["key"]), version=int(value["version"]))
            for value in data.get("skills", [])
        ),
        metadata=dict(data.get("metadata", {})),
        created_at=created_at,
    )
