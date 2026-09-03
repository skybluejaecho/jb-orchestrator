import pytest

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.phase_packs import PhaseInputDefinition, PhasePackDefinition


def test_phase_pack_requires_unique_named_inputs() -> None:
    with pytest.raises(DomainValidationError, match="input keys must be unique"):
        PhasePackDefinition(
            key="implementation",
            version=1,
            name="Implementation",
            description="Implement an approved plan.",
            instructions="Change the repository and report verification.",
            inputs=(
                PhaseInputDefinition(key="plan", description="Approved plan"),
                PhaseInputDefinition(key="plan", description="Duplicate plan"),
            ),
        )


def test_phase_pack_defensively_copies_json_contracts() -> None:
    output_contract = {"required": ["summary", "tests"]}
    phase_pack = PhasePackDefinition(
        key="verification",
        version=1,
        name="Verification",
        description="Verify an implementation.",
        instructions="Run checks and report evidence.",
        output_contract=output_contract,
    )

    output_contract["required"].append("mutated")

    assert phase_pack.output_contract == {"required": ["summary", "tests"]}
