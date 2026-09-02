"""Stable JSON representations for model routing state."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from jb_orchestrator.model_routing.models import (
    ModelProfile,
    ModelRoutingRequest,
    ModelSelection,
    ModelTier,
    NodeModelSelection,
    RequirementLevel,
)


def profile_to_dict(profile: ModelProfile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "key": profile.key,
        "version": profile.version,
        "name": profile.name,
        "provider": profile.provider,
        "model_id": profile.model_id,
        "tier": profile.tier.value,
        "context_window": profile.context_window,
        "input_cost_per_million": str(profile.input_cost_per_million),
        "output_cost_per_million": str(profile.output_cost_per_million),
        "enabled": profile.enabled,
        "capabilities": list(profile.capabilities),
        "executor_keys": list(profile.executor_keys),
        "metadata": profile.metadata,
        "created_at": profile.created_at.isoformat(),
    }


def profile_from_dict(data: dict[str, Any]) -> ModelProfile:
    return ModelProfile(
        id=UUID(str(data["id"])),
        key=str(data["key"]),
        version=int(data["version"]),
        name=str(data["name"]),
        provider=str(data["provider"]),
        model_id=str(data["model_id"]),
        tier=ModelTier(str(data["tier"])),
        context_window=int(data["context_window"]),
        input_cost_per_million=Decimal(str(data["input_cost_per_million"])),
        output_cost_per_million=Decimal(str(data["output_cost_per_million"])),
        enabled=bool(data.get("enabled", True)),
        capabilities=tuple(str(value) for value in data.get("capabilities", [])),
        executor_keys=tuple(str(value) for value in data.get("executor_keys", [])),
        metadata=dict(data.get("metadata", {})),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )


def request_to_dict(request: ModelRoutingRequest) -> dict[str, Any]:
    return {
        "complexity": request.complexity.value,
        "risk": request.risk.value,
        "quality": request.quality.value,
        "required_capabilities": list(request.required_capabilities),
        "estimated_input_tokens": request.estimated_input_tokens,
        "max_output_tokens": request.max_output_tokens,
        "max_cost_usd": str(request.max_cost_usd) if request.max_cost_usd is not None else None,
    }


def request_from_dict(data: dict[str, Any]) -> ModelRoutingRequest:
    budget = data.get("max_cost_usd")
    return ModelRoutingRequest(
        complexity=RequirementLevel(str(data.get("complexity", "medium"))),
        risk=RequirementLevel(str(data.get("risk", "medium"))),
        quality=RequirementLevel(str(data.get("quality", "medium"))),
        required_capabilities=tuple(str(value) for value in data.get("required_capabilities", [])),
        estimated_input_tokens=int(data.get("estimated_input_tokens", 0)),
        max_output_tokens=int(data.get("max_output_tokens", 4096)),
        max_cost_usd=Decimal(str(budget)) if budget is not None else None,
    )


def node_selection_to_dict(value: NodeModelSelection) -> dict[str, Any]:
    selection = value.selection
    return {
        "node_key": value.node_key,
        "profile": profile_to_dict(selection.profile),
        "policy_version": selection.policy_version,
        "required_tier": selection.required_tier.value,
        "estimated_cost_usd": str(selection.estimated_cost_usd),
        "reason_codes": list(selection.reason_codes),
    }


def node_selection_from_dict(data: dict[str, Any]) -> NodeModelSelection:
    return NodeModelSelection(
        node_key=str(data["node_key"]),
        selection=ModelSelection(
            profile=profile_from_dict(dict(data["profile"])),
            policy_version=int(data["policy_version"]),
            required_tier=ModelTier(str(data["required_tier"])),
            estimated_cost_usd=Decimal(str(data["estimated_cost_usd"])),
            reason_codes=tuple(str(value) for value in data.get("reason_codes", [])),
        ),
    )
