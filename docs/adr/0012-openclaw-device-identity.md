# ADR 0012: Persist a dedicated OpenClaw device identity outside workflow state

- Status: Accepted
- Date: 2026-09-02

## Context

Shared Gateway tokens are bootstrap credentials, not durable per-client identities. Reusing them in
every short-lived Bridge process prevents device-scoped revocation and leaves a high-value shared
secret in the steady-state worker environment. The official Gateway client delegates identity,
signing, and device-token storage to its host.

## Decision

The Node Bridge owns one persistent Ed25519 key pair in `JB_OPENCLAW_DEVICE_STATE_DIR`. Its device ID
is the SHA-256 digest of the raw 32-byte public key, matching the OpenClaw identity contract. Every
challenge payload is signed with the private key through `GatewayClientHostDeps`.

The shared Gateway credential is supplied as a one-time bootstrap credential. After the operator
approves the exact pairing request, the Bridge stores the Gateway-issued token keyed by device ID
and role. Later processes prefer that scoped device token and can run without the bootstrap secret.
Token rotation replaces the stored value atomically; authentication rejection can clear it through
the official client callback.

Identity creation uses exclusive file creation so concurrent worker processes converge on the first
successfully persisted key. Token updates use write-then-rename. Files request owner-only mode on
POSIX; Windows deployments must enforce an equivalent NTFS ACL on the state directory.

TLS fingerprint configuration is passed to the official client for `wss://` endpoints. Gateway
credentials, device private keys, and device tokens are never stored in PostgreSQL or passed as
process arguments.

## Consequences

- A paired worker has a stable, independently revocable identity across Bridge processes.
- The shared bootstrap credential can be removed after successful pairing.
- Workflow backups cannot leak Gateway credentials because secrets remain outside the database.
- Losing the device state directory requires a new pairing approval.
- Multi-host workers must use separate state directories and device identities.
