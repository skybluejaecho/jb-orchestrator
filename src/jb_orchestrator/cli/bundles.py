"""Declarative orchestration bundle loading, planning, and application."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jb_orchestrator.api.schemas import (
    ModelProfileCreate,
    PhasePackCreate,
    ProjectCreate,
    SkillCreate,
    WorkflowDefinitionCreate,
)
from jb_orchestrator.config import get_settings
from jb_orchestrator.domain import Project
from jb_orchestrator.domain.exceptions import DomainValidationError
from jb_orchestrator.model_routing import ModelProfile
from jb_orchestrator.phase_packs import PhaseInputDefinition, PhasePackDefinition
from jb_orchestrator.phase_packs.validation import check_output_contract_schema
from jb_orchestrator.skills import SkillDefinition, SkillReference
from jb_orchestrator.workflows import WorkflowDefinitionError
from jb_orchestrator.workflows.models import WorkflowDefinition
from jb_orchestrator.workflows.serialization import edge_from_dict, node_from_dict

MAX_BUNDLE_BYTES = 1_048_576
PROJECTS_PATH = "/v1/projects?limit=500"
VersionedPayload = SkillCreate | ModelProfileCreate | PhasePackCreate | WorkflowDefinitionCreate


class BundleError(RuntimeError):
    """A bundle cannot be loaded, planned, or safely applied."""


class BundleBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
    definition_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=128)
    definition_version: int = Field(ge=1)


class OrchestrationBundle(BaseModel):
    """Versioned, source-controlled inputs for one orchestration installation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    project: ProjectCreate | None = None
    skills: tuple[SkillCreate, ...] = ()
    models: tuple[ModelProfileCreate, ...] = ()
    phase_packs: tuple[PhasePackCreate, ...] = ()
    workflows: tuple[WorkflowDefinitionCreate, ...] = ()
    binding: BundleBinding | None = None

    @model_validator(mode="after")
    def identities_are_unique(self) -> OrchestrationBundle:
        identities_by_label = (
            ("skill", [(value.key, value.version) for value in self.skills]),
            ("model", [(value.key, value.version) for value in self.models]),
            ("phase pack", [(value.key, value.version) for value in self.phase_packs]),
            ("workflow", [(value.key, value.version) for value in self.workflows]),
        )
        for label, identities in identities_by_label:
            if len(identities) != len(set(identities)):
                raise ValueError(f"bundle {label} identities must be unique")
        if (
            self.project is not None
            and self.binding is not None
            and self.binding.project_key != self.project.key
        ):
            raise ValueError("bundle binding project_key must match the bundled project")
        return self


@dataclass(frozen=True, slots=True)
class BundleValidation:
    external_dependencies: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "external_dependencies": list(self.external_dependencies),
            "status": "valid",
        }


class BundleActionKind(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class BundleAction:
    resource: str
    identity: str
    action: BundleActionKind
    detail: str | None = None

    def as_dict(self) -> dict[str, str]:
        value = {
            "resource": self.resource,
            "identity": self.identity,
            "action": self.action.value,
        }
        if self.detail is not None:
            value["detail"] = self.detail
        return value


@dataclass(frozen=True, slots=True)
class BundlePlan:
    actions: tuple[BundleAction, ...]
    external_dependencies: tuple[str, ...]

    @property
    def has_conflicts(self) -> bool:
        return any(action.action is BundleActionKind.CONFLICT for action in self.actions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.as_dict() for action in self.actions],
            "external_dependencies": list(self.external_dependencies),
            "status": "conflict" if self.has_conflicts else "ready",
        }


class BundleClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> Any: ...


class ControlPlaneBundleClient:
    """Authenticated synchronous client used only by the bundle CLI adapter."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.control_plane_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if settings.api_token is not None:
            self._headers["Authorization"] = f"Bearer {settings.api_token.get_secret_value()}"

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                json=dict(payload) if payload is not None else None,
                headers=self._headers,
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            raise BundleError(f"control-plane request failed: {exc}") from exc
        if allow_not_found and response.status_code == 404:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BundleError(
                f"{method} {path} failed: HTTP {response.status_code} {response.text}"
            ) from exc
        return response.json()


def load_bundle(path: Path) -> OrchestrationBundle:
    try:
        if path.stat().st_size > MAX_BUNDLE_BYTES:
            raise BundleError(f"bundle exceeds the {MAX_BUNDLE_BYTES}-byte limit")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BundleError(f"cannot read bundle: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BundleError(f"bundle YAML is invalid: {exc}") from exc
    if not isinstance(raw, dict):
        raise BundleError("bundle root must be a YAML mapping")
    try:
        return OrchestrationBundle.model_validate(raw)
    except ValidationError as exc:
        raise BundleError(f"bundle schema is invalid:\n{exc}") from exc


def validate_bundle(bundle: OrchestrationBundle) -> BundleValidation:
    phases_by_reference = {(value.key, value.version): value for value in bundle.phase_packs}
    try:
        if bundle.project is not None:
            Project(
                key=bundle.project.key,
                name=bundle.project.name,
                repository_url=str(bundle.project.repository_url),
                default_branch=bundle.project.default_branch,
            )
        for skill in bundle.skills:
            SkillDefinition(**skill.model_dump())
        for model in bundle.models:
            ModelProfile(**model.model_dump())
        for phase_pack in bundle.phase_packs:
            check_output_contract_schema(phase_pack.output_contract)
            PhasePackDefinition(
                key=phase_pack.key,
                version=phase_pack.version,
                name=phase_pack.name,
                description=phase_pack.description,
                instructions=phase_pack.instructions,
                inputs=tuple(
                    PhaseInputDefinition(**value.model_dump()) for value in phase_pack.inputs
                ),
                output_contract=phase_pack.output_contract,
                skills=tuple(
                    SkillReference(key=value.key, version=value.version)
                    for value in phase_pack.skills
                ),
                metadata=phase_pack.metadata,
            )
        for workflow in bundle.workflows:
            payload = workflow.model_dump(mode="json")
            WorkflowDefinition(
                key=workflow.key,
                version=workflow.version,
                entry_node=workflow.entry_node,
                nodes=tuple(node_from_dict(value) for value in payload["nodes"]),
                edges=tuple(edge_from_dict(value) for value in payload["edges"]),
            )
            for node in workflow.nodes:
                if node.phase_pack is None:
                    continue
                resolved_phase = phases_by_reference.get(
                    (node.phase_pack.key, node.phase_pack.version)
                )
                if resolved_phase is None:
                    continue
                declared = {value.key: value for value in resolved_phase.inputs}
                mapped = {value.input_key for value in node.input_mappings}
                if not mapped <= set(declared):
                    raise WorkflowDefinitionError(
                        f"node {node.key} maps an undeclared input from {resolved_phase.key}"
                    )
                missing = sorted(
                    key for key, value in declared.items() if value.required and key not in mapped
                )
                if missing:
                    raise WorkflowDefinitionError(
                        f"node {node.key} is missing required phase inputs: {', '.join(missing)}"
                    )
    except (DomainValidationError, WorkflowDefinitionError, KeyError, TypeError, ValueError) as exc:
        raise BundleError(f"bundle contract is invalid: {exc}") from exc

    included_skills = {(value.key, value.version) for value in bundle.skills}
    included_phases = {(value.key, value.version) for value in bundle.phase_packs}
    included_workflows = {(value.key, value.version) for value in bundle.workflows}
    dependencies: set[str] = set()
    for phase_pack in bundle.phase_packs:
        for reference in phase_pack.skills:
            if (reference.key, reference.version) not in included_skills:
                dependencies.add(f"skill:{reference.key}@{reference.version}")
    for workflow in bundle.workflows:
        for node in workflow.nodes:
            for reference in node.skills:
                if (reference.key, reference.version) not in included_skills:
                    dependencies.add(f"skill:{reference.key}@{reference.version}")
            if node.phase_pack is not None:
                phase_reference = node.phase_pack
                if (phase_reference.key, phase_reference.version) not in included_phases:
                    dependencies.add(f"phase_pack:{phase_reference.key}@{phase_reference.version}")
    if bundle.binding is not None:
        workflow_reference = (
            bundle.binding.definition_key,
            bundle.binding.definition_version,
        )
        if workflow_reference not in included_workflows:
            dependencies.add(f"workflow:{workflow_reference[0]}@{workflow_reference[1]}")
    return BundleValidation(tuple(sorted(dependencies)))


def plan_bundle(bundle: OrchestrationBundle, client: BundleClient) -> BundlePlan:
    validation = validate_bundle(bundle)
    actions: list[BundleAction] = []
    project_key = _project_key(bundle)
    projects = (
        cast(list[dict[str, Any]], client.request("GET", PROJECTS_PATH))
        if project_key is not None
        else []
    )
    project = next((value for value in projects if value.get("key") == project_key), None)
    if bundle.project is not None:
        expected = bundle.project.model_dump(mode="json")
        actions.append(_compare_action("project", bundle.project.key, project, expected))

    catalog_specs: tuple[tuple[str, str, Sequence[VersionedPayload]], ...] = (
        ("skill", "/v1/skills", bundle.skills),
        ("model", "/v1/models", bundle.models),
        ("phase_pack", "/v1/phase-packs", bundle.phase_packs),
        ("workflow", "/v1/workflows", bundle.workflows),
    )
    for resource, path, values in catalog_specs:
        for value in values:
            identity = f"{value.key}@{value.version}"
            current = client.request(
                "GET",
                f"{path}/{value.key}?version={value.version}",
                allow_not_found=True,
            )
            actions.append(
                _compare_action(resource, identity, current, value.model_dump(mode="json"))
            )

    dependency_paths = {
        "skill": "/v1/skills",
        "phase_pack": "/v1/phase-packs",
        "workflow": "/v1/workflows",
    }
    for dependency in validation.external_dependencies:
        resource, identity = dependency.split(":", maxsplit=1)
        key, version = identity.rsplit("@", maxsplit=1)
        current = client.request(
            "GET",
            f"{dependency_paths[resource]}/{key}?version={version}",
            allow_not_found=True,
        )
        if current is None:
            actions.append(
                BundleAction(
                    "dependency",
                    dependency,
                    BundleActionKind.CONFLICT,
                    "the referenced external version is not registered",
                )
            )

    if bundle.binding is not None:
        if project is None:
            if bundle.project is None:
                actions.append(
                    BundleAction(
                        "binding",
                        bundle.binding.project_key,
                        BundleActionKind.CONFLICT,
                        "the target project is not registered or included in the bundle",
                    )
                )
            else:
                actions.append(
                    BundleAction(
                        "binding",
                        bundle.binding.project_key,
                        BundleActionKind.UPDATE,
                        "configure after project and workflow creation",
                    )
                )
        else:
            current = client.request(
                "GET",
                f"/v1/projects/{project['id']}/workflow-binding",
                allow_not_found=True,
            )
            expected = {
                "definition_key": bundle.binding.definition_key,
                "definition_version": bundle.binding.definition_version,
            }
            action = (
                BundleActionKind.UNCHANGED
                if current is not None and _contains_expected(current, expected)
                else BundleActionKind.UPDATE
            )
            actions.append(BundleAction("binding", bundle.binding.project_key, action))
    return BundlePlan(tuple(actions), validation.external_dependencies)


def apply_bundle(bundle: OrchestrationBundle, client: BundleClient) -> BundlePlan:
    plan = plan_bundle(bundle, client)
    if plan.has_conflicts:
        conflicts = ", ".join(
            action.identity for action in plan.actions if action.action is BundleActionKind.CONFLICT
        )
        raise BundleError(f"bundle has immutable conflicts; no changes applied: {conflicts}")

    action_by_identity = {
        (action.resource, action.identity): action.action for action in plan.actions
    }
    project: dict[str, Any] | None = None
    if (
        bundle.project is not None
        and action_by_identity[("project", bundle.project.key)] is BundleActionKind.CREATE
    ):
        project = cast(
            dict[str, Any],
            client.request("POST", "/v1/projects", payload=bundle.project.model_dump(mode="json")),
        )
    if project is None and (project_key := _project_key(bundle)) is not None:
        projects = cast(list[dict[str, Any]], client.request("GET", PROJECTS_PATH))
        project = next((value for value in projects if value.get("key") == project_key), None)

    catalog_specs: tuple[tuple[str, str, Sequence[VersionedPayload]], ...] = (
        ("skill", "/v1/skills", bundle.skills),
        ("model", "/v1/models", bundle.models),
        ("phase_pack", "/v1/phase-packs", bundle.phase_packs),
        ("workflow", "/v1/workflows", bundle.workflows),
    )
    for resource, path, values in catalog_specs:
        for value in values:
            identity = f"{value.key}@{value.version}"
            if action_by_identity[(resource, identity)] is BundleActionKind.CREATE:
                client.request("POST", path, payload=value.model_dump(mode="json"))

    if bundle.binding is not None:
        if project is None:
            raise BundleError(f"bundle project does not exist: {bundle.binding.project_key}")
        if action_by_identity[("binding", bundle.binding.project_key)] is BundleActionKind.UPDATE:
            client.request(
                "PUT",
                f"/v1/projects/{project['id']}/workflow-binding",
                payload={
                    "definition_key": bundle.binding.definition_key,
                    "definition_version": bundle.binding.definition_version,
                },
            )
    return plan


def _project_key(bundle: OrchestrationBundle) -> str | None:
    if bundle.project is not None:
        return bundle.project.key
    if bundle.binding is not None:
        return bundle.binding.project_key
    return None


def _compare_action(
    resource: str,
    identity: str,
    current: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> BundleAction:
    if current is None:
        return BundleAction(resource, identity, BundleActionKind.CREATE)
    if _contains_expected(current, expected):
        return BundleAction(resource, identity, BundleActionKind.UNCHANGED)
    return BundleAction(
        resource,
        identity,
        BundleActionKind.CONFLICT,
        "the immutable identity already exists with different content",
    )


def _contains_expected(current: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(current.get(key) == value for key, value in expected.items())
