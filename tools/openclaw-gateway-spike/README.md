# OpenClaw Gateway spike

This isolated tool validates the external-runtime contract before it becomes a production
`jb-orchestrator` executor adapter. It uses the official Gateway client and protocol packages,
pinned to OpenClaw `2026.8.1` and wire protocol v4.

## Validated flow

```text
jb-orchestrator task idempotency key
          |
          v
agent(message, sessionKey, idempotencyKey) -> runId
          |
          +-> agent.wait(runId) -> terminal snapshot
          |
          +-> sessions.abort(runId) on timeout/shutdown/cancellation

next task for the same role/project -> agent(..., same sessionKey, new idempotencyKey)
```

`sessionKey` preserves the OpenClaw-owned conversation. `runId` identifies one active turn, and
the orchestrator's stable task idempotency key prevents duplicate side effects when a worker
retries.

## Install and test

Node.js 22.19 or newer is required.

```powershell
cd tools/openclaw-gateway-spike
npm ci
npm test
```

## Live inspection

Start or provide an OpenClaw Gateway, then set its shared bootstrap credential in the current
shell. Do not put credentials in a committed file. The first attempt creates a persistent Ed25519
identity and can return `PAIRING_REQUIRED` with a request ID.

```powershell
$env:OPENCLAW_GATEWAY_URL = "ws://127.0.0.1:18789"
$env:OPENCLAW_GATEWAY_TOKEN = "<gateway-token>"
npm run inspect
```

On the Gateway host, review and approve that exact request:

```powershell
openclaw devices list
openclaw devices approve <requestId>
```

Run `npm run inspect` again with the bootstrap credential. The Gateway-issued device token is saved
under `JB_OPENCLAW_DEVICE_STATE_DIR` (default `.jb-orchestrator/openclaw-device`). Later processes
reuse that scoped token, so the shared bootstrap credential can be removed from the worker
environment after pairing.

For a remote Gateway, use `wss://` and configure `OPENCLAW_GATEWAY_TLS_FINGERPRINT`. Keep the device
state directory restricted to the worker OS account; on Windows, verify its NTFS ACL explicitly.

Run one turn and wait for its terminal result:

```powershell
npm run run -- --session-key "agent:reviewer:jb-orchestrator" `
  --message "Inspect the current repository state" `
  --idempotency-key "<stable-jb-task-key>"
```

Reuse the same `--session-key` with a new idempotency key to continue that conversation. `Ctrl+C`
or process termination sends `sessions.abort` for the exact active `runId` before disconnecting.

## Spike boundary

The client provides host-owned Ed25519 identity and scoped device-token persistence. The production
deployment must additionally protect the state directory, rotate credentials operationally,
persist the mapping from JB task/run IDs to OpenClaw `sessionKey`/`runId`, and reconcile active runs
after reconnect.

The installable adapter owns the production-boundary acceptance command. After these contract tests
pass, use `uv run jb-openclaw doctor` and the explicitly opted-in `jb-openclaw acceptance` flow
documented in `adapters/openclaw/README.md` against the target deployment.
