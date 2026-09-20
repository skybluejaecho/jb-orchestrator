import pytest

from jb_orchestrator.application.output_contracts import enforce_output_contract
from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.phase_packs import (
    PhasePackDefinition,
    check_output_contract_schema,
    validate_output,
)
from jb_orchestrator.workflows import NodeOutcome


def phase_pack() -> PhasePackDefinition:
    return PhasePackDefinition(
        key="verification",
        version=1,
        name="Verification",
        description="Verify implementation evidence.",
        instructions="Return a structured verdict.",
        output_contract={
            "type": "object",
            "required": ["verdict", "findings"],
            "properties": {
                "verdict": {"enum": ["approved", "rejected"]},
                "findings": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    )


def test_invalid_json_schema_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="valid JSON Schema"):
        check_output_contract_schema({"type": "not-a-json-type"})


def test_external_schema_references_are_rejected() -> None:
    with pytest.raises(DomainValidationError, match="external schema references"):
        check_output_contract_schema(
            {"properties": {"result": {"$ref": "https://example.com/result.json"}}}
        )


def test_output_validation_returns_deterministic_structured_errors() -> None:
    violations = validate_output(phase_pack().output_contract, {"verdict": "unknown"})

    assert [(value.path, value.keyword) for value in violations] == [
        ("$", "required"),
        ("$.verdict", "enum"),
    ]


def test_invalid_success_becomes_repairable_failure() -> None:
    decision = enforce_output_contract(
        phase_pack(),
        NodeOutcome.SUCCESS,
        {"verdict": "unknown"},
    )

    assert decision.outcome is NodeOutcome.FAILURE
    assert decision.rejected
    assert decision.output["rejected_output"] == {"verdict": "unknown"}
    assert decision.output["contract_violation"]["phase_pack"] == {
        "key": "verification",
        "version": 1,
    }


def test_valid_success_and_explicit_failure_are_not_rewritten() -> None:
    valid = {"verdict": "approved", "findings": []}
    accepted = enforce_output_contract(phase_pack(), NodeOutcome.SUCCESS, valid)
    provider_failure = {"error": "provider failed"}
    failed = enforce_output_contract(phase_pack(), NodeOutcome.FAILURE, provider_failure)

    assert accepted.output is valid
    assert accepted.outcome is NodeOutcome.SUCCESS
    assert not accepted.rejected
    assert failed.output is provider_failure
    assert failed.outcome is NodeOutcome.FAILURE
    assert not failed.rejected
