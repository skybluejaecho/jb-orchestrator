from pathlib import Path
from typing import Any

import pytest

from jb_orchestrator.cli.bundles import (
    BundleActionKind,
    BundleError,
    OrchestrationBundle,
    apply_bundle,
    load_bundle,
    plan_bundle,
    validate_bundle,
)


def bundle_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project": {
            "key": "alpha",
            "name": "Alpha",
            "repository_url": "https://example.com/alpha.git",
            "default_branch": "develop",
        },
        "skills": [
            {
                "key": "review",
                "version": 1,
                "name": "Review",
                "description": "Review a result.",
                "source_kind": "local",
                "source_uri": "./skills/review",
                "content_digest": f"sha256:{'a' * 64}",
            }
        ],
        "phase_packs": [
            {
                "key": "implementation",
                "version": 1,
                "name": "Implementation",
                "description": "Implement one bounded task.",
                "instructions": "Implement the requested change.",
                "skills": [{"key": "review", "version": 1}],
                "output_contract": {"type": "object"},
            }
        ],
        "workflows": [
            {
                "key": "delivery",
                "version": 1,
                "entry_node": "implement",
                "nodes": [
                    {
                        "key": "implement",
                        "kind": "task",
                        "executor_key": "openclaw",
                        "phase_pack": {"key": "implementation", "version": 1},
                    },
                    {
                        "key": "done",
                        "kind": "terminal",
                        "terminal_status": "succeeded",
                    },
                    {
                        "key": "failed",
                        "kind": "terminal",
                        "terminal_status": "failed",
                    },
                ],
                "edges": [
                    {"source": "implement", "outcome": "success", "target": "done"},
                    {"source": "implement", "outcome": "failure", "target": "failed"},
                ],
            }
        ],
        "binding": {
            "project_key": "alpha",
            "definition_key": "delivery",
            "definition_version": 1,
        },
    }


class MissingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        allow_not_found: bool = False,
    ) -> Any:
        copied = dict(payload) if payload is not None else None
        self.calls.append((method, path, copied))
        if method == "GET" and path == "/v1/projects?limit=500":
            projects = [
                call[2]
                for call in self.calls
                if call[0:2] == ("POST", "/v1/projects") and call[2] is not None
            ]
            return [
                dict(project, id="00000000-0000-0000-0000-000000000001") for project in projects
            ]
        if method == "GET" and allow_not_found:
            return None
        if method == "POST" and path == "/v1/projects":
            return dict(copied or {}, id="00000000-0000-0000-0000-000000000001")
        return copied or {}


def test_load_and_validate_complete_bundle(tmp_path: Path) -> None:
    path = tmp_path / "orchestrator.yaml"
    path.write_text(
        """schema_version: 1
project:
  key: alpha
  name: Alpha
  repository_url: https://example.com/alpha.git
skills: []
models: []
phase_packs: []
workflows: []
""",
        encoding="utf-8",
    )

    bundle = load_bundle(path)
    result = validate_bundle(bundle)

    assert bundle.project is not None
    assert bundle.project.key == "alpha"
    assert result.external_dependencies == ()


def test_validation_rejects_invalid_workflow_graph() -> None:
    payload = bundle_payload()
    payload["workflows"][0]["entry_node"] = "missing"
    bundle = OrchestrationBundle.model_validate(payload)

    with pytest.raises(BundleError, match="entry node does not exist"):
        validate_bundle(bundle)


def test_validation_reuses_project_domain_rules() -> None:
    payload = bundle_payload()
    payload["project"]["key"] = "invalid_project"
    payload["binding"]["project_key"] = "invalid_project"
    bundle = OrchestrationBundle.model_validate(payload)

    with pytest.raises(BundleError, match="project key"):
        validate_bundle(bundle)


def test_validation_reports_dependencies_outside_bundle() -> None:
    payload = bundle_payload()
    payload["skills"] = []
    bundle = OrchestrationBundle.model_validate(payload)

    result = validate_bundle(bundle)

    assert result.external_dependencies == ("skill:review@1",)


def test_plan_rejects_missing_external_dependency() -> None:
    payload = bundle_payload()
    payload["skills"] = []
    bundle = OrchestrationBundle.model_validate(payload)

    plan = plan_bundle(bundle, MissingClient())

    assert plan.has_conflicts
    dependency = next(action for action in plan.actions if action.resource == "dependency")
    assert dependency.identity == "skill:review@1"
    assert dependency.action is BundleActionKind.CONFLICT


def test_plan_rejects_binding_to_missing_external_project() -> None:
    payload = bundle_payload()
    payload["project"] = None
    bundle = OrchestrationBundle.model_validate(payload)

    plan = plan_bundle(bundle, MissingClient())

    binding = next(action for action in plan.actions if action.resource == "binding")
    assert binding.action is BundleActionKind.CONFLICT


def test_plan_marks_missing_resources_without_writing() -> None:
    bundle = OrchestrationBundle.model_validate(bundle_payload())
    client = MissingClient()

    plan = plan_bundle(bundle, client)

    assert [action.action for action in plan.actions] == [
        BundleActionKind.CREATE,
        BundleActionKind.CREATE,
        BundleActionKind.CREATE,
        BundleActionKind.CREATE,
        BundleActionKind.UPDATE,
    ]
    assert all(method == "GET" for method, _, _ in client.calls)


def test_apply_uses_dependency_order() -> None:
    bundle = OrchestrationBundle.model_validate(bundle_payload())
    client = MissingClient()

    apply_bundle(bundle, client)

    writes = [(method, path) for method, path, _ in client.calls if method != "GET"]
    assert writes == [
        ("POST", "/v1/projects"),
        ("POST", "/v1/skills"),
        ("POST", "/v1/phase-packs"),
        ("POST", "/v1/workflows"),
        ("PUT", "/v1/projects/00000000-0000-0000-0000-000000000001/workflow-binding"),
    ]


def test_reapplying_matching_bundle_performs_no_writes() -> None:
    bundle = OrchestrationBundle.model_validate(bundle_payload())

    class ExistingClient(MissingClient):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.calls.append((method, path, kwargs.get("payload")))
            if method != "GET":
                raise AssertionError(f"unexpected write: {method} {path}")
            if path == "/v1/projects?limit=500":
                assert bundle.project is not None
                return [
                    bundle.project.model_dump(mode="json")
                    | {"id": "00000000-0000-0000-0000-000000000001"}
                ]
            if path == "/v1/projects/00000000-0000-0000-0000-000000000001/workflow-binding":
                assert bundle.binding is not None
                return {
                    "definition_key": bundle.binding.definition_key,
                    "definition_version": bundle.binding.definition_version,
                }
            values = (*bundle.skills, *bundle.models, *bundle.phase_packs, *bundle.workflows)
            for value in values:
                if f"/{value.key}?version={value.version}" in path:
                    return value.model_dump(mode="json") | {"id": "ignored"}
            return None

    client = ExistingClient()

    plan = apply_bundle(bundle, client)

    assert not plan.has_conflicts
    assert all(action.action is BundleActionKind.UNCHANGED for action in plan.actions)


def test_apply_rejects_immutable_conflict_before_writing() -> None:
    bundle = OrchestrationBundle.model_validate(bundle_payload())

    class ConflictingClient(MissingClient):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            if method == "GET" and path == "/v1/projects?limit=500":
                return [
                    {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "key": "alpha",
                        "name": "Different",
                        "repository_url": "https://example.com/alpha.git",
                        "default_branch": "develop",
                    }
                ]
            return super().request(method, path, **kwargs)

    client = ConflictingClient()

    with pytest.raises(BundleError, match="no changes applied"):
        apply_bundle(bundle, client)

    assert all(method == "GET" for method, _, _ in client.calls)
