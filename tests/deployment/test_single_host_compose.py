from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
COMPOSE_PATH = ROOT / "deploy" / "single-host" / "compose.yml"


def compose() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8")))


def test_default_core_has_migration_and_health_dependencies() -> None:
    services = compose()["services"]

    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["readiness-monitor"]["depends_on"] == services["api"]["depends_on"]
    assert services["api"]["environment"]["JB_API_AUTH_ENABLED"] == "true"
    assert services["api"]["restart"] == "unless-stopped"


def test_optional_runtime_roles_use_independent_profiles() -> None:
    services = compose()["services"]

    assert services["task-worker"]["profiles"] == ["execution"]
    assert services["scm-worker"]["profiles"] == ["scm"]
    assert services["notification-worker"]["profiles"] == ["notifications"]
    assert services["jarvis"]["profiles"] == ["jarvis"]
    assert services["admin"]["profiles"] == ["tools"]


def test_provider_credentials_are_confined_to_owning_process() -> None:
    services = compose()["services"]
    all_environment = {
        name: set(service.get("environment", {})) for name, service in services.items()
    }

    assert "OPENCLAW_GATEWAY_TOKEN" in all_environment["task-worker"]
    assert "JB_GITHUB_TOKEN" in all_environment["scm-worker"]
    assert "JB_WEBHOOK_DESTINATIONS" in all_environment["notification-worker"]
    assert "JARVIS_API_TOKEN" in all_environment["jarvis"]
    assert all(
        "OPENCLAW_GATEWAY_TOKEN" not in keys
        for name, keys in all_environment.items()
        if name != "task-worker"
    )
    assert all(
        "JB_GITHUB_TOKEN" not in keys
        for name, keys in all_environment.items()
        if name != "scm-worker"
    )


def test_task_and_scm_workers_share_stable_workspace_paths_and_scope() -> None:
    services = compose()["services"]
    task_volumes = services["task-worker"]["volumes"]
    scm_volumes = services["scm-worker"]["volumes"]

    assert any(volume.endswith(":/workspaces/repositories") for volume in task_volumes)
    assert any(volume.endswith(":/workspaces/worktrees") for volume in task_volumes)
    assert set(scm_volumes).issubset(set(task_volumes))
    scope_index = services["scm-worker"]["command"].index("--workspace-scope") + 1
    assert services["scm-worker"]["command"][scope_index] == (
        "git-worktree:06fbb7af18b23cb00bbe0ce1adc5e555d51716290a1839f7b736445226e100f6"
    )


def test_durable_and_rebuildable_state_are_separate_volumes() -> None:
    volumes = compose()["volumes"]

    assert set(volumes) == {"openclaw-device", "postgres-data", "skill-cache"}
    assert "postgres-data:/var/lib/postgresql/data" in compose()["services"]["postgres"]["volumes"]
