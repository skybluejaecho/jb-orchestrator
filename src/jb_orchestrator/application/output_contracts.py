"""Application policy for turning invalid phase output into repairable failure data."""

from dataclasses import dataclass
from typing import Any

from jb_orchestrator.phase_packs import PhasePackDefinition, validate_output
from jb_orchestrator.workflows import NodeOutcome


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputContractDecision:
    outcome: NodeOutcome
    output: dict[str, Any]
    rejected: bool = False


def enforce_output_contract(
    phase_pack: PhasePackDefinition | None,
    outcome: NodeOutcome,
    output: dict[str, Any],
) -> OutputContractDecision:
    """Convert invalid successful output to a failure artifact for graph routing."""

    if phase_pack is None or outcome is not NodeOutcome.SUCCESS or not phase_pack.output_contract:
        return OutputContractDecision(outcome=outcome, output=output)

    violations = validate_output(phase_pack.output_contract, output)
    if not violations:
        return OutputContractDecision(outcome=outcome, output=output)

    return OutputContractDecision(
        outcome=NodeOutcome.FAILURE,
        output={
            "contract_violation": {
                "reason": "output_contract_violation",
                "phase_pack": {
                    "key": phase_pack.key,
                    "version": phase_pack.version,
                },
                "errors": [
                    {
                        "path": value.path,
                        "message": value.message,
                        "keyword": value.keyword,
                    }
                    for value in violations
                ],
            },
            "rejected_output": output,
        },
        rejected=True,
    )
