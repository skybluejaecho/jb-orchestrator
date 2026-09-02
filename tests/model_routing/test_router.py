from decimal import Decimal

import pytest

from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    ModelProfile,
    ModelRoutingError,
    ModelRoutingRequest,
    ModelTier,
    RequirementLevel,
)


def profile(
    key: str,
    tier: ModelTier,
    *,
    input_cost: str,
    output_cost: str,
    context_window: int = 128_000,
    capabilities: tuple[str, ...] = ("coding",),
    executor_keys: tuple[str, ...] = ("codex",),
    version: int = 1,
    enabled: bool = True,
) -> ModelProfile:
    return ModelProfile(
        key=key,
        version=version,
        name=key,
        provider="openai",
        model_id=key,
        tier=tier,
        context_window=context_window,
        input_cost_per_million=Decimal(input_cost),
        output_cost_per_million=Decimal(output_cost),
        enabled=enabled,
        capabilities=capabilities,
        executor_keys=executor_keys,
    )


def test_low_risk_work_uses_cheapest_sufficient_tier() -> None:
    router = DeterministicModelRouter()
    request = ModelRoutingRequest(
        complexity=RequirementLevel.LOW,
        risk=RequirementLevel.LOW,
        quality=RequirementLevel.LOW,
        required_capabilities=("coding",),
        estimated_input_tokens=10_000,
        max_output_tokens=2_000,
    )

    selection = router.route(
        request,
        (
            profile("economy-b", ModelTier.ECONOMY, input_cost="0.5", output_cost="2"),
            profile("advanced", ModelTier.ADVANCED, input_cost="5", output_cost="20"),
            profile("economy-a", ModelTier.ECONOMY, input_cost="0.2", output_cost="1"),
        ),
        executor_key="codex",
    )

    assert selection.profile.key == "economy-a"
    assert selection.required_tier is ModelTier.ECONOMY
    assert selection.estimated_cost_usd == Decimal("0.004")


@pytest.mark.parametrize(
    ("field", "level"),
    [
        ("complexity", RequirementLevel.HIGH),
        ("risk", RequirementLevel.CRITICAL),
        ("quality", RequirementLevel.HIGH),
    ],
)
def test_high_requirement_forces_advanced_tier(field: str, level: RequirementLevel) -> None:
    values = {
        "complexity": RequirementLevel.LOW,
        "risk": RequirementLevel.LOW,
        "quality": RequirementLevel.LOW,
        field: level,
    }
    request = ModelRoutingRequest(**values)  # type: ignore[arg-type]

    selection = DeterministicModelRouter().route(
        request,
        (
            profile("economy", ModelTier.ECONOMY, input_cost="0", output_cost="0"),
            profile("advanced", ModelTier.ADVANCED, input_cost="5", output_cost="20"),
        ),
        executor_key="codex",
    )

    assert selection.profile.key == "advanced"
    assert selection.required_tier is ModelTier.ADVANCED


def test_router_filters_executor_capability_and_context() -> None:
    request = ModelRoutingRequest(
        required_capabilities=("vision",),
        estimated_input_tokens=100_000,
        max_output_tokens=10_000,
    )

    selection = DeterministicModelRouter().route(
        request,
        (
            profile(
                "wrong-executor",
                ModelTier.BALANCED,
                input_cost="0",
                output_cost="0",
                capabilities=("vision",),
                executor_keys=("orca",),
            ),
            profile(
                "small-context",
                ModelTier.BALANCED,
                input_cost="0",
                output_cost="0",
                context_window=64_000,
                capabilities=("vision",),
            ),
            profile(
                "no-vision",
                ModelTier.BALANCED,
                input_cost="0",
                output_cost="0",
            ),
            profile(
                "valid",
                ModelTier.BALANCED,
                input_cost="1",
                output_cost="4",
                capabilities=("coding", "vision"),
            ),
        ),
        executor_key="codex",
    )

    assert selection.profile.key == "valid"
    assert "capabilities:vision" in selection.reason_codes


def test_router_never_silently_exceeds_budget() -> None:
    request = ModelRoutingRequest(
        estimated_input_tokens=100_000,
        max_output_tokens=10_000,
        max_cost_usd=Decimal("0.01"),
    )

    with pytest.raises(ModelRoutingError, match="no model profile"):
        DeterministicModelRouter().route(
            request,
            (profile("costly", ModelTier.BALANCED, input_cost="1", output_cost="4"),),
            executor_key="codex",
        )


def test_router_never_selects_disabled_profile() -> None:
    disabled = profile(
        "disabled",
        ModelTier.BALANCED,
        input_cost="0",
        output_cost="0",
        enabled=False,
    )

    with pytest.raises(ModelRoutingError, match="no model profile"):
        DeterministicModelRouter().route(ModelRoutingRequest(), (disabled,), executor_key="codex")


def test_latest_version_wins_deterministic_tie() -> None:
    profiles = (
        profile("same", ModelTier.BALANCED, input_cost="1", output_cost="1", version=1),
        profile("same", ModelTier.BALANCED, input_cost="1", output_cost="1", version=2),
    )

    selection = DeterministicModelRouter().route(
        ModelRoutingRequest(), profiles, executor_key="codex"
    )

    assert selection.profile.version == 2
