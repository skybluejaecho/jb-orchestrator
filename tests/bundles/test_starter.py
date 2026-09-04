from pathlib import Path

import pytest

from jb_orchestrator.cli.bundles import load_bundle, validate_bundle
from jb_orchestrator.cli.starter import StarterKitError, initialize_starter_kit
from jb_orchestrator.skills.materialization import compute_directory_digest
from jb_orchestrator.workflows import NodeKind, NodeOutcome


def test_starter_kit_contains_valid_bundle_and_verified_skills(tmp_path: Path) -> None:
    destination = initialize_starter_kit(tmp_path / "orchestration")

    bundle = load_bundle(destination / "orchestrator.yaml")
    validation = validate_bundle(bundle)

    assert validation.external_dependencies == ()
    assert {value.key for value in bundle.phase_packs} == {
        "implementation",
        "planning",
        "repair",
        "review-synthesis",
        "verification",
    }
    assert {value.key for value in bundle.workflows} == {
        "parallel-verification",
        "planning-only",
        "standard-delivery",
    }
    standard = next(value for value in bundle.workflows if value.key == "standard-delivery")
    assert any(
        edge.source == "repair"
        and edge.outcome is NodeOutcome.SUCCESS
        and edge.target == "implement"
        for edge in standard.edges
    )
    parallel = next(value for value in bundle.workflows if value.key == "parallel-verification")
    assert {node.kind for node in parallel.nodes} >= {NodeKind.FORK, NodeKind.JOIN}
    split_targets = {edge.target for edge in parallel.edges if edge.source == "split-reviews"}
    assert split_targets == {"functional-review", "risk-review"}
    repair = next(value for value in bundle.phase_packs if value.key == "repair")
    assert len(repair.skills) == 2
    for skill in bundle.skills:
        assert compute_directory_digest(destination / "skills" / skill.source_uri) == (
            skill.content_digest
        )


def test_starter_kit_refuses_to_overwrite_existing_directory(tmp_path: Path) -> None:
    destination = tmp_path / "orchestration"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(StarterKitError, match="already exists"):
        initialize_starter_kit(destination)

    assert marker.read_text(encoding="utf-8") == "keep"
