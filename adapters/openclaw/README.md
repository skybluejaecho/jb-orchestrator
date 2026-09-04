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
bootstrap credentials are inherited by the Node subprocess through `OPENCLAW_GATEWAY_TOKEN` or
`OPENCLAW_GATEWAY_PASSWORD` and are never passed in command arguments or stored in workflow rows.

The first connection creates an Ed25519 identity below `JB_OPENCLAW_DEVICE_STATE_DIR`. Approve the
reported request with `openclaw devices approve <requestId>`, then connect once more with the
bootstrap credential. The issued operator device token is persisted and used by later bridge
processes without the shared credential. Protect this directory with OS-account-only permissions.
For remote `wss://` Gateways, set `OPENCLAW_GATEWAY_TLS_FINGERPRINT`.

## Node configuration

An OpenClaw workflow task may set these values in its node `configuration`:

- `agent_id`: target OpenClaw agent
- `session_key`: explicit durable session key; otherwise a deterministic execution/node key is used
- `cwd`: agent working directory
- `thinking`: OpenClaw thinking level

The selected JB model profile supplies the OpenClaw provider and model override. Verified skill
entrypoint paths are appended to the task message so the agent receives the exact materialized
versions selected by the workflow snapshot.

When a phase defines an output contract, the adapter asks the agent for one JSON object without a
Markdown fence. An object returned in `agent.wait.output`, or a string containing a JSON object, is
stored as the task artifact and validated against that contract. The complete provider terminal
result remains in the external execution ledger. Non-JSON output retains a diagnostic provider
envelope and will follow the workflow failure edge when it violates a phase contract.

## Recovery behavior

- `starting` without a run ID repeats `agent` with the same idempotency key.
- `active` resumes `agent.wait` without starting another run.
- terminal records return their persisted normalized result without contacting OpenClaw.
- worker timeout, lease loss, or shutdown calls `sessions.abort` for the recorded exact run ID.

Before a non-loopback production deployment, validate pairing, TLS pinning, reconnect event
reconciliation, filesystem ACLs, and credential rotation against the deployed Gateway version.
