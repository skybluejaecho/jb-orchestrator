from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
SERVER_COMPOSE_PATH = ROOT / "deploy" / "server" / "compose.yml"
JARVIS_COMPOSE_PATH = ROOT / "deploy" / "clients" / "jarvis" / "compose.yml"


def load_compose(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def server_compose() -> dict[str, Any]:
    return load_compose(SERVER_COMPOSE_PATH)


def jarvis_compose() -> dict[str, Any]:
    return load_compose(JARVIS_COMPOSE_PATH)


def test_server_core_has_migration_and_health_dependencies() -> None:
    services = server_compose()["services"]

    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["readiness-monitor"]["depends_on"] == services["api"]["depends_on"]
    assert services["api"]["environment"]["JB_API_AUTH_ENABLED"] == "true"
    assert services["api"]["restart"] == "unless-stopped"


def test_server_contains_no_jarvis_or_jarvis_credentials() -> None:
    services = server_compose()["services"]
    all_environment = {
        name: set(service.get("environment", {})) for name, service in services.items()
    }

    assert "jarvis" not in services
    assert all("JARVIS_API_TOKEN" not in keys for keys in all_environment.values())
    assert all("JARVIS_CONTROL_PLANE_URL" not in keys for keys in all_environment.values())


def test_server_api_is_loopback_bound_by_default() -> None:
    api_ports = server_compose()["services"]["api"]["ports"]

    assert api_ports == ["${JB_API_BIND_ADDRESS:-127.0.0.1}:${JB_API_PORT:-8000}:8000"]


def test_optional_server_roles_use_independent_profiles() -> None:
    services = server_compose()["services"]

    assert services["task-worker"]["profiles"] == ["execution"]
    assert services["scm-worker"]["profiles"] == ["scm"]
    assert services["notification-worker"]["profiles"] == ["notifications"]
    assert services["admin"]["profiles"] == ["tools"]


def test_provider_credentials_are_confined_to_owning_server_process() -> None:
    services = server_compose()["services"]
    all_environment = {
        name: set(service.get("environment", {})) for name, service in services.items()
    }

    assert "OPENCLAW_GATEWAY_TOKEN" in all_environment["task-worker"]
    assert "JB_GITHUB_TOKEN" in all_environment["scm-worker"]
    assert "JB_WEBHOOK_DESTINATIONS" in all_environment["notification-worker"]
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
    services = server_compose()["services"]
    task_volumes = services["task-worker"]["volumes"]
    scm_volumes = services["scm-worker"]["volumes"]

    assert any(volume.endswith(":/workspaces/repositories") for volume in task_volumes)
    assert any(volume.endswith(":/workspaces/worktrees") for volume in task_volumes)
    assert set(scm_volumes).issubset(set(task_volumes))
    scope_index = services["scm-worker"]["command"].index("--workspace-scope") + 1
    assert services["scm-worker"]["command"][scope_index] == (
        "git-worktree:06fbb7af18b23cb00bbe0ce1adc5e555d51716290a1839f7b736445226e100f6"
    )


def test_durable_and_rebuildable_server_state_are_separate_volumes() -> None:
    volumes = server_compose()["volumes"]

    assert set(volumes) == {"openclaw-device", "postgres-data", "skill-cache"}
    assert (
        "postgres-data:/var/lib/postgresql/data"
        in server_compose()["services"]["postgres"]["volumes"]
    )


def test_jarvis_client_is_standalone_and_loopback_only() -> None:
    services = jarvis_compose()["services"]
    jarvis = services["jarvis"]

    assert set(services) == {"jarvis"}
    assert "depends_on" not in jarvis
    assert jarvis["ports"] == ["127.0.0.1:${JB_JARVIS_PORT:-3300}:3300"]
    assert set(jarvis["environment"]) == {
        "JARVIS_CONTROL_PLANE_URL",
        "JARVIS_API_TOKEN",
    }
    assert jarvis["extra_hosts"] == ["host.docker.internal:host-gateway"]
    assert "/api/projects" in " ".join(jarvis["healthcheck"]["test"])
    assert jarvis["restart"] == "unless-stopped"
