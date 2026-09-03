"""JSON Schema validation for phase-pack output contracts."""

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from jb_orchestrator.domain.exceptions import DomainValidationError


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputContractViolation:
    path: str
    message: str
    keyword: str | None


def check_output_contract_schema(contract: dict[str, Any]) -> None:
    """Reject malformed contracts when a phase-pack version is registered."""

    _reject_external_references(contract)
    try:
        Draft202012Validator.check_schema(contract)
    except SchemaError as exc:
        raise DomainValidationError(
            f"phase pack output_contract is not a valid JSON Schema: {exc.message}"
        ) from exc


def _reject_external_references(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if (
                key in {"$ref", "$dynamicRef"}
                and isinstance(nested, str)
                and not nested.startswith("#")
            ):
                raise DomainValidationError(
                    "phase pack output_contract external schema references are not allowed"
                )
            _reject_external_references(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_external_references(nested)


def validate_output(
    contract: dict[str, Any], output: dict[str, Any]
) -> tuple[OutputContractViolation, ...]:
    """Return deterministic, structured validation failures for one task output."""

    validator = Draft202012Validator(contract)
    errors = sorted(
        validator.iter_errors(output),
        key=lambda value: (
            tuple(str(part) for part in value.absolute_path),
            value.message,
        ),
    )
    return tuple(
        OutputContractViolation(
            path=_json_path(tuple(error.absolute_path)),
            message=error.message,
            keyword=str(error.validator) if error.validator is not None else None,
        )
        for error in errors
    )


def _json_path(parts: tuple[Any, ...]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path
