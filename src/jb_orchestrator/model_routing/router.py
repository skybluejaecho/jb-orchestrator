"""Deterministic, fail-closed model routing policy."""

from collections.abc import Sequence
from decimal import Decimal

from jb_orchestrator.model_routing.models import (
    ModelProfile,
    ModelRoutingRequest,
    ModelSelection,
    ModelTier,
    RequirementLevel,
)

POLICY_VERSION = 1
_TIER_RANK = {ModelTier.ECONOMY: 0, ModelTier.BALANCED: 1, ModelTier.ADVANCED: 2}
_LEVEL_RANK = {
    RequirementLevel.LOW: 0,
    RequirementLevel.MEDIUM: 1,
    RequirementLevel.HIGH: 2,
    RequirementLevel.CRITICAL: 2,
}
_MILLION = Decimal(1_000_000)


class ModelRoutingError(RuntimeError):
    """No registered model safely satisfies a routing request."""


class DeterministicModelRouter:
    policy_version = POLICY_VERSION

    def route(
        self,
        request: ModelRoutingRequest,
        profiles: Sequence[ModelProfile],
        *,
        executor_key: str,
    ) -> ModelSelection:
        required_tier = self.required_tier(request)
        required_capabilities = set(request.required_capabilities)
        candidates: list[tuple[ModelProfile, Decimal]] = []
        for profile in profiles:
            if not profile.enabled:
                continue
            if _TIER_RANK[profile.tier] < _TIER_RANK[required_tier]:
                continue
            if profile.executor_keys and executor_key not in profile.executor_keys:
                continue
            if not required_capabilities.issubset(profile.capabilities):
                continue
            if profile.context_window < request.required_context:
                continue
            cost = self.estimate_cost(profile, request)
            if request.max_cost_usd is not None and cost > request.max_cost_usd:
                continue
            candidates.append((profile, cost))
        if not candidates:
            raise ModelRoutingError(
                "no model profile satisfies tier, executor, capability, "
                "context, and budget constraints"
            )
        profile, cost = min(
            candidates,
            key=lambda item: (
                _TIER_RANK[item[0].tier],
                item[1],
                item[0].key,
                -item[0].version,
            ),
        )
        reasons = [
            f"required_tier:{required_tier.value}",
            f"selected_tier:{profile.tier.value}",
            f"executor:{executor_key}",
        ]
        if request.required_capabilities:
            reasons.append("capabilities:" + ",".join(request.required_capabilities))
        if request.max_cost_usd is not None:
            reasons.append("budget_satisfied")
        return ModelSelection(
            profile=profile,
            policy_version=self.policy_version,
            required_tier=required_tier,
            estimated_cost_usd=cost,
            reason_codes=tuple(reasons),
        )

    @staticmethod
    def required_tier(request: ModelRoutingRequest) -> ModelTier:
        rank = max(
            _LEVEL_RANK[request.complexity],
            _LEVEL_RANK[request.risk],
            _LEVEL_RANK[request.quality],
        )
        return (ModelTier.ECONOMY, ModelTier.BALANCED, ModelTier.ADVANCED)[rank]

    @staticmethod
    def estimate_cost(profile: ModelProfile, request: ModelRoutingRequest) -> Decimal:
        return (
            Decimal(request.estimated_input_tokens) * profile.input_cost_per_million
            + Decimal(request.max_output_tokens) * profile.output_cost_per_million
        ) / _MILLION
