import json
from pathlib import Path

import pytest
import yaml

from tools.release.verify_version import component_versions, verify_version

ROOT = Path(__file__).parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "container-images.yml"
RUNTIME_DOCKERFILE = ROOT / "deploy" / "server" / "Dockerfile.runtime"


def load_workflow(path: Path) -> dict[str, object]:
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def write_component_versions(root: Path, runtime: str, jarvis: str) -> None:
    (root / "apps" / "jarvis").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "{runtime}"\n', encoding="utf-8"
    )
    (root / "apps" / "jarvis" / "package.json").write_text(
        json.dumps({"version": jarvis}), encoding="utf-8"
    )


def test_release_version_requires_a_stable_matching_version(tmp_path: Path) -> None:
    write_component_versions(tmp_path, "1.2.3", "1.2.3")

    assert verify_version("v1.2.3", tmp_path) == "1.2.3"
    assert component_versions(tmp_path) == {"runtime": "1.2.3", "jarvis": "1.2.3"}

    with pytest.raises(ValueError, match="stable SemVer"):
        verify_version("v1.2.3-rc.1", tmp_path)

    write_component_versions(tmp_path, "1.2.3", "1.2.4")
    with pytest.raises(ValueError, match=r"jarvis=1\.2\.4"):
        verify_version("v1.2.3", tmp_path)


def test_ci_builds_and_verifies_both_container_images() -> None:
    jobs = load_workflow(CI_WORKFLOW)["jobs"]
    assert isinstance(jobs, dict)
    quality_commands = "\n".join(step.get("run", "") for step in jobs["quality"]["steps"])
    build = jobs["container-build"]
    assert isinstance(build, dict)
    matrix = build["strategy"]["matrix"]["include"]

    assert {entry["component"] for entry in matrix} == {"runtime", "jarvis"}
    assert all(entry["dockerfile"].startswith("deploy/") for entry in matrix)
    assert "uv export --frozen --no-dev --no-emit-project" in quality_commands
    assert "git diff --exit-code -- deploy/server/requirements.lock" in quality_commands
    assert "container-build" in jobs["release-readiness"]["needs"]


def test_runtime_image_uses_the_hash_locked_dependency_export() -> None:
    dockerfile = RUNTIME_DOCKERFILE.read_text(encoding="utf-8")

    assert "deploy/server/requirements.lock" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "--no-deps" in dockerfile
    assert "python -m pip check" in dockerfile


def test_release_publishes_only_versioned_and_commit_tags() -> None:
    workflow = load_workflow(RELEASE_WORKFLOW)
    trigger = workflow["on"]
    assert trigger == {"push": {"tags": ["v*.*.*"]}}

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    publish = jobs["publish"]
    assert publish["needs"] == "validate-release"
    assert publish["permissions"] == {"contents": "read", "packages": "write"}

    metadata = next(step for step in publish["steps"] if step.get("id") == "metadata")
    tags = metadata["with"]["tags"]
    assert "type=semver,pattern={{version}}" in tags
    assert "type=sha,prefix=sha-" in tags
    assert metadata["with"]["flavor"] == "latest=false"

    image_names = {entry["image"] for entry in publish["strategy"]["matrix"]["include"]}
    assert image_names == {"jb-orchestrator-runtime", "jb-orchestrator-jarvis"}
