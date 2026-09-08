# Single-host runtime composition

This directory is the operational reference for one trusted Docker host. PostgreSQL, migrations,
the Control Plane, and the readiness monitor form the default core. Task execution, SCM publication,
notifications, Jarvis, and one-shot administration are explicit Compose profiles.

## Prepare

Copy the environment template without committing the resulting file:

```powershell
Copy-Item deploy/single-host/.env.example deploy/single-host/.env
```

Set a random PostgreSQL password. Enable only the credentials required by selected profiles. The
task and SCM containers share the exact `/workspaces/worktrees` and `/workspaces/repositories`
paths, so their durable workspace scope remains stable.

Validate interpolation before building or starting anything:

```powershell
docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml --profile "*" config --quiet
```

## Start

Start the database, apply migrations once, then keep the API and readiness monitor running:

```powershell
docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml up -d --build
```

Add only the capabilities this host owns:

```powershell
docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml --profile execution up -d

docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml --profile scm --profile notifications up -d

docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml --profile jarvis up -d
```

Profiles can be combined in one call. A profile never injects its credentials into unrelated
containers.

## Bootstrap service accounts

The API stores only token hashes. Issue each token once from an admin container and save its output
directly in the secret manager or ignored `.env` file. For example, Jarvis generally needs project
read, dispatch, approval, cancellation, workspace, SCM, and notification permissions required by
the enabled UI actions.

```powershell
docker compose --env-file deploy/single-host/.env `
  -f deploy/single-host/compose.yml --profile tools run --rm admin auth issue `
  --key jarvis --name Jarvis --all-projects `
  --permission project.read --permission request.dispatch `
  --permission run.approve --permission run.cancel
```

Inspect the current permission enum with `docker compose ... run --rm admin auth issue --help`
before granting optional workspace, SCM, or notification operations. Restart Jarvis after placing
the issued token in `JARVIS_API_TOKEN`.

## Network boundary

The API port is plain HTTP and must remain behind a trusted host firewall or HTTPS reverse proxy.
Production Jarvis must use the externally reachable HTTPS URL in `JARVIS_CONTROL_PLANE_URL`; the
Compose file deliberately does not invent certificates or DNS ownership. OpenClaw defaults to a
Gateway on the Docker host. A remote Gateway must use `wss://` and a pinned TLS fingerprint.

## Persistent state and recovery

- `postgres-data` is the orchestration source of truth and must be backed up.
- `openclaw-device` contains the paired OpenClaw identity and device token; restrict access.
- `skill-cache` is verified, content-addressed, and can be rebuilt.
- `JB_REPOSITORY_ROOT` and `JB_WORKTREE_ROOT` are host bind mounts retained for review and recovery.

Do not run `docker compose down --volumes` as an ordinary restart operation. It removes durable
PostgreSQL and OpenClaw device state. Use `stop` or `down` without `--volumes` instead.
