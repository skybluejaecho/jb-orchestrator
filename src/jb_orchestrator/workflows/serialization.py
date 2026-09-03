"""Stable JSON representations for workflow definitions and snapshots."""

from datetime import datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.model_routing.serialization import (
    node_selection_from_dict,
    node_selection_to_dict,
    request_from_dict,
    request_to_dict,
)
from jb_orchestrator.phase_packs import PhasePackReference
from jb_orchestrator.phase_packs.serialization import phase_pack_from_dict, phase_pack_to_dict
from jb_orchestrator.skills import SkillReference
from jb_orchestrator.skills.serialization import skill_from_dict, skill_to_dict
from jb_orchestrator.workflows.models import (
    EdgeDefinition,
    NodeDefinition,
    NodeInputMapping,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowRequestContext,
    WorkflowSnapshot,
    WorkflowStatus,
)


def node_to_dict(node: NodeDefinition) -> dict[str, Any]:
    return {
        "key": node.key,
        "kind": node.kind.value,
        "max_attempts": node.max_attempts,
        "max_visits": node.max_visits,
        "timeout_seconds": node.timeout_seconds,
        "terminal_status": node.terminal_status.value if node.terminal_status else None,
        "executor_key": node.executor_key,
        "instructions": node.instructions,
        "configuration": node.configuration,
        "skills": [
            {"key": reference.key, "version": reference.version} for reference in node.skills
        ],
        "model_routing": (
            request_to_dict(node.model_routing) if node.model_routing is not None else None
        ),
        "phase_pack": (
            {"key": node.phase_pack.key, "version": node.phase_pack.version}
            if node.phase_pack is not None
            else None
        ),
        "input_mappings": [
            {"input_key": value.input_key, "source_node": value.source_node}
            for value in node.input_mappings
        ],
    }


def node_from_dict(data: dict[str, Any]) -> NodeDefinition:
    terminal = data.get("terminal_status")
    model_routing = data.get("model_routing")
    phase_pack = data.get("phase_pack")
    return NodeDefinition(
        key=str(data["key"]),
        kind=NodeKind(str(data["kind"])),
        max_attempts=int(data["max_attempts"]),
        max_visits=int(data["max_visits"]),
        timeout_seconds=int(data["timeout_seconds"]),
        terminal_status=WorkflowStatus(str(terminal)) if terminal else None,
        executor_key=str(data["executor_key"]) if data.get("executor_key") else None,
        instructions=str(data["instructions"]) if data.get("instructions") else None,
        configuration=dict(data.get("configuration", {})),
        skills=tuple(
            SkillReference(key=str(reference["key"]), version=int(reference["version"]))
            for reference in data.get("skills", [])
        ),
        model_routing=(
            request_from_dict(dict(model_routing)) if model_routing is not None else None
        ),
        phase_pack=(
            PhasePackReference(key=str(phase_pack["key"]), version=int(phase_pack["version"]))
            if isinstance(phase_pack, dict)
            else None
        ),
        input_mappings=tuple(
            NodeInputMapping(
                input_key=str(value["input_key"]), source_node=str(value["source_node"])
            )
            for value in data.get("input_mappings", [])
        ),
    )


def edge_to_dict(edge: EdgeDefinition) -> dict[str, str]:
    return {"source": edge.source, "outcome": edge.outcome.value, "target": edge.target}


def edge_from_dict(data: dict[str, Any]) -> EdgeDefinition:
    return EdgeDefinition(
        source=str(data["source"]),
        outcome=NodeOutcome(str(data["outcome"])),
        target=str(data["target"]),
    )


def definition_to_dict(definition: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": str(definition.id),
        "key": definition.key,
        "version": definition.version,
        "entry_node": definition.entry_node,
        "nodes": [node_to_dict(node) for node in definition.nodes],
        "edges": [edge_to_dict(edge) for edge in definition.edges],
    }


def definition_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=UUID(str(data["id"])),
        key=str(data["key"]),
        version=int(data["version"]),
        entry_node=str(data["entry_node"]),
        nodes=tuple(node_from_dict(node) for node in data["nodes"]),
        edges=tuple(edge_from_dict(edge) for edge in data["edges"]),
    )


def request_context_to_dict(context: WorkflowRequestContext) -> dict[str, Any]:
    return {
        "request_id": str(context.request_id),
        "project_id": str(context.project_id),
        "project_key": context.project_key,
        "project_name": context.project_name,
        "repository_url": context.repository_url,
        "default_branch": context.default_branch,
        "prompt": context.prompt,
        "title": context.title,
    }


def request_context_from_dict(data: dict[str, Any]) -> WorkflowRequestContext:
    return WorkflowRequestContext(
        request_id=UUID(str(data["request_id"])),
        project_id=UUID(str(data["project_id"])),
        project_key=str(data["project_key"]),
        project_name=str(data["project_name"]),
        repository_url=str(data["repository_url"]),
        default_branch=str(data["default_branch"]),
        prompt=str(data["prompt"]),
        title=str(data["title"]) if data.get("title") is not None else None,
    )


def snapshot_to_dict(snapshot: WorkflowSnapshot) -> dict[str, Any]:
    return {
        "id": str(snapshot.id),
        "run_id": str(snapshot.run_id),
        "definition_id": str(snapshot.definition_id),
        "definition_key": snapshot.definition_key,
        "definition_version": snapshot.definition_version,
        "entry_node": snapshot.entry_node,
        "nodes": [node_to_dict(node) for node in snapshot.nodes],
        "edges": [edge_to_dict(edge) for edge in snapshot.edges],
        "request_context": (
            request_context_to_dict(snapshot.request_context)
            if snapshot.request_context is not None
            else None
        ),
        "phase_packs": [phase_pack_to_dict(value) for value in snapshot.phase_packs],
        "created_at": snapshot.created_at.isoformat(),
        "skills": [skill_to_dict(skill) for skill in snapshot.skills],
        "model_selections": [node_selection_to_dict(value) for value in snapshot.model_selections],
    }


def snapshot_from_dict(data: dict[str, Any]) -> WorkflowSnapshot:
    request_context = data.get("request_context")
    return WorkflowSnapshot(
        id=UUID(str(data["id"])),
        run_id=UUID(str(data["run_id"])),
        definition_id=UUID(str(data["definition_id"])),
        definition_key=str(data["definition_key"]),
        definition_version=int(data["definition_version"]),
        entry_node=str(data["entry_node"]),
        nodes=tuple(node_from_dict(node) for node in data["nodes"]),
        edges=tuple(edge_from_dict(edge) for edge in data["edges"]),
        request_context=(
            request_context_from_dict(request_context)
            if isinstance(request_context, dict)
            else None
        ),
        phase_packs=tuple(phase_pack_from_dict(value) for value in data.get("phase_packs", [])),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        skills=tuple(skill_from_dict(skill) for skill in data.get("skills", [])),
        model_selections=tuple(
            node_selection_from_dict(value) for value in data.get("model_selections", [])
        ),
    )
