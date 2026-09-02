# JB OpenClaw executor

Optional executor package connecting `jb-orchestrator` workers to an OpenClaw Gateway through the
official Node.js client.

## Development installation

```powershell
cd tools/openclaw-gateway-spike
npm ci
cd ../..
uv pip install --no-deps -e adapters/openclaw
uv run jb-worker --list-executors
```

The executor key is `openclaw`. Installing this package registers its entry point; the core package
does not claim OpenClaw tasks by default.

Set `JB_OPENCLAW_BRIDGE_PATH` if the bridge is not at the repository-relative default. Gateway
credentials are inherited by the Node subprocess through `OPENCLAW_GATEWAY_TOKEN` or
`OPENCLAW_GATEWAY_PASSWORD` and are never passed in command arguments or stored in workflow rows.

## Node configuration

An OpenClaw workflow task may set these values in its node `configuration`:

- `agent_id`: target OpenClaw agent
- `session_key`: explicit durable session key; otherwise a deterministic execution/node key is used
- `cwd`: agent working directory
- `thinking`: OpenClaw thinking level

The selected JB model profile supplies the OpenClaw provider and model override. Verified skill
entrypoint paths are appended to the task message so the agent receives the exact materialized
versions selected by the workflow snapshot.

## Recovery behavior

- `starting` without a run ID repeats `agent` with the same idempotency key.
- `active` resumes `agent.wait` without starting another run.
- terminal records return their persisted normalized result without contacting OpenClaw.
- worker timeout, lease loss, or shutdown calls `sessions.abort` for the recorded exact run ID.

This first adapter uses shared Gateway authentication with the ORCH-013 token-only bridge. Before a
non-loopback production deployment, add host-owned device identity/token persistence and validate
pairing, TLS pinning, reconnect event reconciliation, and credential rotation against the deployed
Gateway version.
