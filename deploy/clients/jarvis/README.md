# Local Jarvis client

Jarvis runs on a trusted user workstation as a local web client. The browser opens only
http://127.0.0.1:3300, while Jarvis server routes call the remote Control Plane with a dedicated
service-account token. The remote server does not expose a Jarvis UI or Jarvis port.

## Prepare

~~~powershell
Copy-Item deploy/clients/jarvis/.env.example deploy/clients/jarvis/.env
~~~

Configure:

- JARVIS_CONTROL_PLANE_URL with a Control Plane URL reachable through VPN, SSH tunnel, or HTTPS.
- JARVIS_API_TOKEN with a distinct least-privilege token issued for this workstation.
- JB_JARVIS_PORT only when local port 3300 is already occupied.

For an installed client, set JB_JARVIS_IMAGE to an explicit published version such as
ghcr.io/skybluejaecho/jb-orchestrator-jarvis:0.1.0. Do not use a floating tag. Authenticate the
workstation first when the GHCR package is private. Keep the development image value only when
intentionally building from the checked-out source with --build.

Do not put the token in a URL, commit it, or reuse a server or Worker credential.

Validate the local composition:

~~~powershell
docker compose --env-file deploy/clients/jarvis/.env `
  -f deploy/clients/jarvis/compose.yml config --quiet
~~~

## Start

~~~powershell
docker compose --env-file deploy/clients/jarvis/.env `
  -f deploy/clients/jarvis/compose.yml pull

docker compose --env-file deploy/clients/jarvis/.env `
  -f deploy/clients/jarvis/compose.yml up -d
~~~

Open http://127.0.0.1:3300. The published port is fixed to the loopback interface, so another
machine cannot open this Jarvis instance through the workstation's LAN address.

Inspect status and logs:

~~~powershell
docker compose --env-file deploy/clients/jarvis/.env `
  -f deploy/clients/jarvis/compose.yml ps

docker compose --env-file deploy/clients/jarvis/.env `
  -f deploy/clients/jarvis/compose.yml logs --tail 100 jarvis
~~~

## Connection options

For an SSH tunnel, forward a client-host port to a Control Plane that is bound to the server
loopback interface:

~~~powershell
ssh -L 18000:127.0.0.1:8000 user@server-ip
~~~

Then set JARVIS_CONTROL_PLANE_URL to http://host.docker.internal:18000. The Compose mapping makes
that host alias available on Linux Docker as well as Docker Desktop. For a private VPN, use the
server's VPN address. Public HTTP is never an acceptable transport for the service-account token.
