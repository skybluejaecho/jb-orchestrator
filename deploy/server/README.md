# Server runtime composition

This composition runs only the jb-orchestrator server roles on one trusted Docker host. PostgreSQL,
migrations, the Control Plane API, and the readiness monitor form the default core. Task execution,
SCM publication, notifications, and one-shot administration remain explicit Compose profiles.
Jarvis is not deployed on this host.

## Prepare

~~~powershell
Copy-Item deploy/server/.env.example deploy/server/.env
~~~

Replace JB_POSTGRES_PASSWORD with a long random value and configure credentials only for the
profiles this host owns. The API is published on 127.0.0.1 by default.

- Keep the default when clients connect through an SSH tunnel.
- For a private VPN, set JB_API_BIND_ADDRESS to the server's VPN interface address.
- Do not use 0.0.0.0 or a public interface before a separately managed HTTPS reverse proxy and
  firewall policy are in place.

Validate interpolation before building or starting anything:

~~~powershell
docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml --profile "*" config --quiet
~~~

For an operational deployment, set JB_RUNTIME_IMAGE to an explicit published version such as
ghcr.io/skybluejaecho/jb-orchestrator-runtime:0.1.0. Do not use a floating tag. Authenticate the
Docker host first when the GHCR package is private. Leave the development image value unchanged
only when intentionally building from the checked-out source with --build.

## Start

Start the database, apply migrations once, then keep the API and readiness monitor running:

~~~powershell
docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml pull

docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml up -d
~~~

Add only the capabilities this host owns:

~~~powershell
docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml --profile execution up -d

docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml --profile scm --profile notifications up -d
~~~

## Issue a Jarvis client account

Issue a distinct least-privilege service account for each Jarvis installation. The token is shown
only once, so move it directly to that client host's ignored environment file or secret store.

~~~powershell
docker compose --env-file deploy/server/.env `
  -f deploy/server/compose.yml --profile tools run --rm admin auth issue `
  --key jarvis-desktop --name "Jarvis Desktop" --all-projects `
  --permission project.read --permission request.dispatch `
  --permission workflow.approve --permission run.cancel `
  --permission workspace.manage --permission scm.publish `
  --permission notification.manage
~~~

Omit write permissions that this client does not need. Revoke only this service account when the
client is retired or lost.

## Persistent state and recovery

- postgres-data is the orchestration source of truth and must be backed up.
- openclaw-device contains the paired OpenClaw identity and device token.
- skill-cache is verified, content-addressed, and rebuildable.
- JB_REPOSITORY_ROOT and JB_WORKTREE_ROOT are host bind mounts retained for review and recovery.

Do not use docker compose down --volumes for an ordinary restart. It removes durable PostgreSQL and
OpenClaw device state. Use stop or down without --volumes instead.

## Migrate from the former single-host composition

Move server values from the former deploy/single-host/.env into deploy/server/.env. The Compose
project and volume names changed. On a host with real data, inspect the existing volumes and use an
explicit backup and restore instead of assuming Docker will attach them under the new names.
